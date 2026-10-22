import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "l3cube-pune/mahahate-multi-roberta"

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Using device:", device)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32
).to(device)

model.eval()

comments = [
    "हा माणूस खूप चांगला आहे",
    "तुमचे खूप खूप आभार",
    "आजचा व्हिडिओ खूप छान आहे",
    "You are amazing bro",
    "हा video खूप छान आहे bro",
    "मला हा विचार आवडला नाही",
    "तू मूर्ख आहेस",
    "This is a test comment",
]

inputs = tokenizer(
    comments,
    padding=True,
    truncation=True,
    max_length=128,
    return_tensors="pt"
).to(device)

with torch.inference_mode():
    outputs = model(**inputs)
    probabilities = torch.softmax(outputs.logits.float(), dim=-1)

for comment, probs in zip(comments, probabilities):
    idx = probs.argmax().item()
    label = model.config.id2label[idx]
    score = probs[idx].item()

    print(f"\nComment: {comment}")
    print(f"Prediction: {label}")
    print(f"Confidence: {score:.4f}")
