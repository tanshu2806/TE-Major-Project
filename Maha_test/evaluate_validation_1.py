import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, f1_score, classification_report

MODEL_NAME = "l3cube-pune/mahahate-multi-roberta"

df = pd.read_excel("hate_valid.xlsx").dropna(subset=["text", "label"])
device = "cuda" if torch.cuda.is_available() else "cpu"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
).to(device)
model.eval()

print("Model label mapping:", model.config.id2label)
print("Device:", device)

# Derive the mapping from the model configuration.
label_map = {
    str(label).lower(): dataset_label
    for label, dataset_label in [
        ("hate", "HATE"),
        ("offensive", "OFFN"),
        ("profane", "PRFN"),
        ("none", "NOT"),
    ]
}
id_to_dataset_label = {
    int(idx): label_map[label.lower()] for idx, label in model.config.id2label.items()
}

predictions = []
batch_size = 8

for start in range(0, len(df), batch_size):
    texts = df["text"].iloc[start : start + batch_size].astype(str).tolist()
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=256,
        return_tensors="pt",
    ).to(device)

    with torch.inference_mode():
        logits = model(**inputs).logits

    indices = logits.argmax(dim=-1).cpu().tolist()
    predictions.extend(id_to_dataset_label[i] for i in indices)

df["predicted_label"] = predictions

labels = ["HATE", "OFFN", "PRFN", "NOT"]

print("Accuracy:", accuracy_score(df["label"], predictions))
print(
    "Macro F1:",
    f1_score(df["label"], predictions, labels=labels, average="macro", zero_division=0),
)
print(classification_report(df["label"], predictions, labels=labels, zero_division=0))

df.to_excel("mahahate_validation_predictions.xlsx", index=False)
print("Saved: mahahate_validation_predictions.xlsx")
