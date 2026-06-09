import sys
import os
import torch
from datasets import load_dataset
from gliner2 import GLiNER2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.pipeline.pipeline import run as hybrid_pipeline_run
from app.pipeline.structural_stage import LABELS

def evaluate_pipeline(name, dataset, pipeline_func):
    IGNORED_LABELS = {"TIME", "DATE", "AGE", "CURRENCY", "URL"}
    total_expected = 0
    total_caught = 0
    false_positives = 0
    total_predicted = 0

    print(f"\n--- Running {name} ---", flush=True)
    for i, row in enumerate(dataset):
        text = row["source_text"]
        ground_truth = row.get("privacy_mask", [])
        sensitive_gt = [g for g in ground_truth if g["label"] not in IGNORED_LABELS]
        
        predicted_spans = pipeline_func(text)
        total_predicted += len(predicted_spans)
        
        # Recall
        for gt in sensitive_gt:
            total_expected += 1
            gt_start, gt_end = gt["start"], gt["end"]
            caught = False
            for pred in predicted_spans:
                # Need to handle different span object types (Detection vs dict)
                p_start = getattr(pred, "start", pred.get("start", 0) if isinstance(pred, dict) else 0)
                p_end = getattr(pred, "end", pred.get("end", 0) if isinstance(pred, dict) else 0)
                if max(gt_start, p_start) < min(gt_end, p_end):
                    caught = True
                    break
            if caught:
                total_caught += 1
                
        # Precision
        for pred in predicted_spans:
            p_start = getattr(pred, "start", pred.get("start", 0) if isinstance(pred, dict) else 0)
            p_end = getattr(pred, "end", pred.get("end", 0) if isinstance(pred, dict) else 0)
            valid = False
            for gt in ground_truth:
                if max(gt["start"], p_start) < min(gt["end"], p_end):
                    valid = True
                    break
            if not valid:
                false_positives += 1

    recall = (total_caught / total_expected) * 100 if total_expected > 0 else 0
    precision = ((total_predicted - false_positives) / total_predicted) * 100 if total_predicted > 0 else 0
    print(f"Results for {name}:")
    print(f"  Recall: {recall:.2f}% | Precision: {precision:.2f}% | Expected: {total_expected} | Caught: {total_caught}")

def main():
    print("Loading HuggingFace Dataset...", flush=True)
    # Use a different seed and range to get a fresh 1000 names dataset
    dataset = load_dataset("ai4privacy/pii-masking-300k", split="train[:20000]")
    dataset = dataset.filter(lambda x: x["language"] == "English")
    # Fresh 1000 payload slice with different seed
    dataset = dataset.shuffle(seed=99).select(range(1000)) 

    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # 1. Pipeline: What we made (Dynamic Hybrid)
    def run_hybrid(text):
        _, detections, _ = hybrid_pipeline_run(text)
        return detections

    evaluate_pipeline("1. Hybrid Pipeline (Dynamic + Regex)", dataset, run_hybrid)

if __name__ == "__main__":
    main()
