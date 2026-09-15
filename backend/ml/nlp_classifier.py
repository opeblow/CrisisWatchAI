"""Multi-label crisis-text classifier built on DistilBERT.

Classifies free-text crisis reports (news articles, observer notes, tweets, ...)
into one or more event categories::

    [conflict, flood, earthquake, epidemic, drought, cyclone, food_crisis, displacement]

The primary implementation fine-tunes ``distilbert-base-uncased`` with a
``MultiLabel`` classification head (BCE logits + sigmoid, threshold ``0.5``).

When ``transformers`` / ``torch`` are not installed the module transparently
falls back to a lightweight keyword-based scorer so demos and smoke tests keep
working in minimal environments.

Typical usage::

    from backend.ml.nlp_classifier import NLPCrisisClassifier, LABELS

    nlp = NLPCrisisClassifier()
    nlp.train(texts=["...earthquake strikes...", ...], labels=[["earthquake"], ...])
    result = nlp.predict("Magnitude 7.2 earthquake rocks the region, hundreds displaced")
    # -> {"labels": ["earthquake", "displacement"], "scores": [0.98, 0.61]}
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

logger = logging.getLogger(__name__)

try:  # Optional heavy dependencies - the module must remain importable without them.
    import torch
    from transformers import (
        AdamW,
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )
    _TRANSFORMERS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - environment dependent
    _TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers/torch not available (%s); using keyword fallback", exc)
    torch = None
    AdamW = AutoModelForSequenceClassification = AutoTokenizer = None
    get_linear_schedule_with_warmup = None

LABELS: List[str] = [
    "conflict",
    "flood",
    "earthquake",
    "epidemic",
    "drought",
    "cyclone",
    "food_crisis",
    "displacement",
]
LABEL_TO_INDEX: Dict[str, int] = {name: i for i, name in enumerate(LABELS)}

MODEL_DIR: Path = Path(__file__).resolve().parent / "models"
NLP_MODEL_DIR: Path = MODEL_DIR / "nlp_distilbert"
META_PATH: Path = NLP_MODEL_DIR / "meta.json"

MAX_SEQ_LENGTH: int = 128
DEFAULT_THRESHOLD: float = 0.5

# Keyword -> (aliases) used by the fallback classifier.  Kept purposefully
# small to limit false positives; real deployments should use the transformer.
_FALLBACK_KEYWORDS: Dict[str, List[str]] = {
    "conflict": [
        "conflict", "war", "battle", "gunfire", "shooting", "bomb", "airstrike",
        "shelling", "militia", "insurgent", "offensive", "ceasefire", "armed",
        "kill", "killed", "fired upon", "clash",
    ],
    "flood": [
        "flood", "flooding", "flash flood", "monsoon", "downpour", "overflow",
        "rising water", "inundat", "swollen river", "torrential rain",
    ],
    "earthquake": [
        "earthquake", "quake", "aftershock", "seismic", "tremor", "magnitude",
        "epicenter", "epicentre", "tectonic",
    ],
    "epidemic": [
        "epidemic", "outbreak", "cholera", "ebola", "measles", "dengue",
        "malaria", "pandemic", "infected", "infection cases",
    ],
    "drought": [
        "drought", "dry spell", "water shortage", "crop failure", "rainfall deficit",
        "scarce rainfall", "reservoir", "depleted groundwater", "arid",
    ],
    "cyclone": [
        "cyclone", "hurricane", "typhoon", "storm surge", "gale", "high winds",
        "tropical storm",
    ],
    "food_crisis": [
        "food", "hunger", "malnutrition", "grain shortage", "food prices",
        "staple crops", "famine", "food insecurity", "empty shelves",
    ],
    "displacement": [
        "displace", "displaced", "refugee", "evacuee", "evacuation", "idp",
        "internally displaced", "fleeing", "fled", "shelter", "makeshift camp",
    ],
}

_WORD_RE = re.compile(r"\b" + r"[\w']+" + r"\b")

__all__ = [
    "NLPCrisisClassifier",
    "LABELS",
    "LABEL_TO_INDEX",
    "DEFAULT_THRESHOLD",
    "_TRANSFORMERS_AVAILABLE",
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


class NLPCrisisClassifier:
    """Multi-label crisis text classifier.

    Attributes
    ----------
    model / tokenizer
        Fitted ``AutoModelForSequenceClassification`` / ``AutoTokenizer`` or
        ``None`` in fallback mode.
    threshold : float
        Sigmoid decision threshold applied to each label.
    """

    def __init__(
        self,
        model_name: str = "distilbert-base-uncased",
        threshold: float = DEFAULT_THRESHOLD,
        model_dir: Union[str, Path] = NLP_MODEL_DIR,
    ) -> None:
        self.model_name = model_name
        self.threshold = float(threshold)
        self.model_dir = Path(model_dir)
        self.model: Any = None
        self.tokenizer: Any = None
        self.device: Any = None
        self._fallback_mode = not _TRANSFORMERS_AVAILABLE
        self._trained_labels: List[str] = list(LABELS)

    # ------------------------------------------------------------------ train
    def train(
        self,
        texts: Sequence[str],
        labels: Sequence[Any],
        epochs: int = 3,
        lr: float = 2e-5,
        batch_size: int = 16,
        val_fraction: float = 0.15,
        random_state: int = 42,
        max_length: int = MAX_SEQ_LENGTH,
        save: bool = True,
    ) -> Dict[str, Any]:
        """Fine-tune DistilBERT for multi-label classification.

        Parameters
        ----------
        texts
            Raw text documents.
        labels
            Per-document multi-label annotations.  Each entry may be a sequence of
            label strings (``["flood", "displacement"]``), a sequence of int
            indices, or a fixed-length binary vector of length ``len(LABELS)``.
        epochs, lr, batch_size
            Training hyper-parameters (defaults 3 / 2e-5 / 16).
        val_fraction
            Fraction of documents held out to track validation BCE loss.
        save
            Persist the fine-tuned model with :meth:`save_model`.

        Returns
        -------
        dict
            Training summary including per-epoch train/val loss, best validation
            loss, active labels and the device used.
        """
        if self._fallback_mode:
            raise RuntimeError(
                "transformers/torch are not installed - cannot fine-tune DistilBERT. "
                "Install them via the backend requirements, or use the keyword fallback "
                "with predict() directly."
            )

        if len(texts) == 0 or len(labels) == 0:
            raise ValueError("texts and labels must not be empty")
        if len(texts) != len(labels):
            raise ValueError(f"texts ({len(texts)}) and labels ({len(labels)}) length mismatch")

        X = [str(t) for t in texts]
        y = self._to_binary_matrix(labels)

        if val_fraction > 0:
            from sklearn.model_selection import train_test_split

            primary = np.argmax(y, axis=1)
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=val_fraction, random_state=random_state, stratify=primary
            )
        else:
            X_train, X_val, y_train, y_val = X, [], y, np.zeros((0, y.shape[1]))

        n_active = int(y.sum(axis=0).astype(bool).sum())
        logger.info(
            "Fine-tuning %s - %d documents (%.0f%% validation), %d/%d active labels",
            self.model_name, len(X_train), val_fraction * 100, n_active, y.shape[1],
        )

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=len(LABELS),
            id2label={i: name for i, name in enumerate(LABELS)},
            label2id=LABEL_TO_INDEX,
        )
        model.to(self.device)

        train_loader = self._build_loader(tokenizer, X_train, y_train, batch_size, shuffle=True)
        val_loader = self._build_loader(tokenizer, X_val, y_val, batch_size, shuffle=False)

        optimizer = AdamW(model.parameters(), lr=lr, correct_bias=False)
        total_steps = len(train_loader) * epochs
        scheduler = get_linear_schedule_with_warmup(
            optimizer, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps
        )
        pos_weight = torch.tensor(
            ((len(y_train) - y_train.sum(axis=0)) / np.maximum(y_train.sum(axis=0), 1)).astype(
                "float32"
            ),
            device=self.device,
        )
        loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)

        epoch_metrics: List[Dict[str, float]] = []
        best_val_loss = float("inf")
        best_state: Optional[Dict[str, Any]] = None

        for epoch in range(1, epochs + 1):
            model.train()
            train_loss, n_batches = 0.0, 0
            for batch in train_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                optimizer.zero_grad()
                outputs = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    labels=batch["labels"],
                )
                loss = outputs["loss"] if isinstance(outputs, dict) else outputs.loss
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                train_loss += loss.item()
                n_batches += 1

            val_loss = self._compute_loss(model, loss_fn, val_loader) if len(X_val) > 0 else float("nan")
            epoch_metrics.append(
                {"epoch": epoch, "train_loss": train_loss / max(n_batches, 1), "val_loss": val_loss}
            )
            logger.info("Epoch %d/%d - train_loss=%.4f val_loss=%s", epoch, epochs, epoch_metrics[-1]["train_loss"], val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

        if best_state is not None:
            model.load_state_dict(best_state)
            logger.info("Restored best checkpoint (val_loss=%.4f)", best_val_loss)

        self.model = model
        self.tokenizer = tokenizer
        self._fallback_mode = False

        if save:
            self.save_model()

        return {
            "epochs": epochs,
            "device": str(self.device),
            "best_val_loss": float(best_val_loss),
            "epoch_metrics": epoch_metrics,
            "active_labels": [LABELS[i] for i in np.where(y.sum(axis=0) > 0)[0]],
            "threshold": self.threshold,
        }

    def predict(self, text: str) -> Dict[str, List[float]]:
        """Classify a single text document.

        Returns ``{"labels": List[str], "scores": List[float]}``.  Only labels whose
        score meets (or exceeds) ``self.threshold`` are returned; ``scores`` are the
        sigmoid probabilities for those labels, sorted descending.
        """
        if not isinstance(text, str) or not text.strip():
            return {"labels": [], "scores": []}

        if self._fallback_mode or self.model is None:
            return self._predict_fallback(text)

        batch = self.tokenizer(
            [text], padding=True, truncation=True, max_length=MAX_SEQ_LENGTH, return_tensors="pt"
        )
        batch = {k: v.to(self.device) for k, v in batch.items()}
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(**batch)
            logits = outputs["logits"] if isinstance(outputs, dict) else outputs.logits
        probs = torch.sigmoid(logits[0]).detach().cpu().numpy()

        return self._format_probs(probs)

    # ------------------------------------------------------------ persistence
    def save_model(self, path: Optional[Union[str, Path]] = None) -> Path:
        """Persist tokenizer, model and metadata via ``transformers``."""
        dest = Path(path) if path else self.model_dir
        dest.parent.mkdir(parents=True, exist_ok=True)

        if self._fallback_mode or self.model is None:
            meta = {
                "mode": "fallback",
                "labels": LABELS,
                "threshold": self.threshold,
                "note": "No trained transformer - keyword fallback will be used on load.",
            }
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "meta.json").write_text(json.dumps(meta, indent=2))
            logger.warning("No transformer to save; wrote fallback metadata to %s", dest)
            return dest

        self.tokenizer.save_pretrained(str(dest))
        self.model.save_pretrained(str(dest))
        (dest / "meta.json").write_text(
            json.dumps(
                {"mode": "transformer", "model_name": self.model_name, "threshold": self.threshold},
                indent=2,
            )
        )
        logger.info("Saved NLP model to %s", dest)
        return dest

    def load_model(self, path: Optional[Union[str, Path]] = None) -> "NLPCrisisClassifier":
        """Load a previously saved DistilBERT model + tokenizer."""
        src = Path(path) if path else self.model_dir
        if not (src / "config.json").exists():
            if (src / "meta.json").exists() and json.loads(
                (src / "meta.json").read_text()
            ).get("mode") == "fallback":
                self._fallback_mode = True
                logger.warning("Loaded fallback NLP classifier metadata from %s", src)
                return self
            raise FileNotFoundError(f"No saved NLP model found at {src}")

        self.tokenizer = AutoTokenizer.from_pretrained(str(src))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(src))
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self._fallback_mode = False
        logger.info("Loaded NLP model from %s", src)
        return self

    # --------------------------------------------------------------- fallback
    def _predict_fallback(self, text: str) -> Dict[str, List[float]]:
        """Keyword-based scorer used when transformers/torch are unavailable."""
        normalized = _normalize_text(text)
        tokens = set(_WORD_RE.findall(normalized))
        hits: Dict[str, int] = {}
        for label, keywords in _FALLBACK_KEYWORDS.items():
            count = 0
            for kw in keywords:
                if kw in normalized or kw in tokens:
                    count += 1
            if count:
                hits[label] = count

        matched = []
        scores = []
        for label, count in sorted(hits.items(), key=lambda kv: kv[1], reverse=True):
            score = min(1.0, count / 2.0)  # one clean hit => 0.5, two or more => 1.0
            if score >= self.threshold:
                matched.append(label)
                scores.append(float(score))
        return {"labels": matched, "scores": scores}

    def _format_probs(self, probs: Sequence[float]) -> Dict[str, List[float]]:
        ranked = sorted(
            ((LABELS[i], float(p)) for i, p in enumerate(probs) if float(p) >= self.threshold),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return {"labels": [name for name, _ in ranked], "scores": [s for _, s in ranked]}

    # --------------------------------------------------------------- helpers
    def _to_binary_matrix(self, labels: Sequence[Any]) -> np.ndarray:
        """Convert flexible label annotations into an (N, len(LABELS)) binary matrix."""
        matrix = np.zeros((len(labels), len(LABELS)), dtype="float32")
        for i, ann in enumerate(labels):
            ann_arr = np.asarray(ann)
            if ann_arr.ndim == 0 or ann_arr.size == 0:
                raise ValueError(f"Empty label annotation at index {i}")
            if ann_arr.dtype.kind in "fcb" and ann_arr.size == len(LABELS) and ann_arr.ndim == 1:
                matrix[i] = (ann_arr > 0).astype("float32")
                continue
            flat = list(ann_arr.ravel()) if ann_arr.ndim else [ann_arr.item()]
            for item in flat:
                if isinstance(item, str):
                    label = item.strip().lower()
                    if label not in LABEL_TO_INDEX:
                        logger.warning("Unknown label %r at index %d - ignored", item, i)
                        continue
                    matrix[i, LABEL_TO_INDEX[label]] = 1.0
                elif isinstance(item, (int, np.integer)):
                    if not (0 <= int(item) < len(LABELS)):
                        raise ValueError(f"Label index {item} out of range at index {i}")
                    matrix[i, int(item)] = 1.0
                else:
                    raise TypeError(f"Unsupported label {item!r} at index {i}")
        return matrix

    def _build_loader(self, tokenizer, texts, labels, batch_size, shuffle):
        encodings = tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
            return_tensors="pt",
        )
        dataset = torch.utils.data.TensorDataset(
            encodings["input_ids"],
            encodings["attention_mask"],
            torch.tensor(np.asarray(labels, dtype="float32")),
        )
        return torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)

    def _compute_loss(self, model, loss_fn, loader) -> float:
        model.eval()
        total, n = 0.0, 0
        with torch.no_grad():
            for batch in loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                outputs = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    labels=batch["labels"],
                )
                loss = outputs["loss"] if isinstance(outputs, dict) else outputs.loss
                total += loss.item()
                n += 1
        return total / max(n, 1)