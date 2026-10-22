import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    f1_score,
)

MODEL_NAME = "l3cube-pune/mahahate-multi-roberta"
INPUT_FILE = "hate_test.xlsx"
OUTPUT_FILE = "mahahate_test_predictions.xlsx"

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Device:", device)

df = pd.read_excel(INPUT_FILE)
df = df.dropna(subset=["text", "label"]).copy()

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
).to(device)
model.eval()

# Official model labels mapped to dataset labels
id_to_dataset_label = {
    0: "HATE",
    1: "OFFN",
    2: "PRFN",
    3: "NOT",
}

predictions = []
confidences = []

batch_size = 8

for start in range(0, len(df), batch_size):
    batch_texts = df["text"].iloc[start : start + batch_size].astype(str).tolist()

    inputs = tokenizer(
        batch_texts,
        padding=True,
        truncation=True,
        max_length=256,
        return_tensors="pt",
    ).to(device)

    with torch.inference_mode():
        logits = model(**inputs).logits
        probs = torch.softmax(logits.float(), dim=-1)

    scores, indices = probs.max(dim=-1)

    predictions.extend(id_to_dataset_label[i.item()] for i in indices)
    confidences.extend(scores.cpu().tolist())

    if (start // batch_size) % 25 == 0:
        print(f"Processed {min(start + batch_size, len(df))}/{len(df)}")

df["predicted_label"] = predictions
df["confidence"] = confidences

labels = ["HATE", "OFFN", "PRFN", "NOT"]

print("\nAccuracy:", round(accuracy_score(df["label"], df["predicted_label"]), 4))
print(
    "Macro F1:",
    round(
        f1_score(
            df["label"],
            df["predicted_label"],
            labels=labels,
            average="macro",
            zero_division=0,
        ),
        4,
    ),
)

print("\nClassification report:")
print(
    classification_report(
        df["label"],
        df["predicted_label"],
        labels=labels,
        zero_division=0,
    )
)

print("\nConfusion matrix (rows=true, columns=predicted):")
print(confusion_matrix(df["label"], df["predicted_label"], labels=labels))

df.to_excel(OUTPUT_FILE, index=False)
print(f"\nSaved predictions to {OUTPUT_FILE}")
