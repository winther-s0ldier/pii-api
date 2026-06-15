import os
import sys
import ast
import pandas as pd
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.pipeline import pipeline

def evaluate():
    # Load dataset
    csv_path = os.path.join(os.path.dirname(__file__), 'data', 'external_dataset', 'pii_dataset.csv')
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: Dataset not found at {csv_path}. Please ensure the dataset is downloaded.")
        return
    except pd.errors.ParserError:
        print(f"Error: Dataset at {csv_path} is malformed.")
        return
    
    # Random subset of 10 rows to fit within local limits
    sample_size = min(10, len(df))
    if sample_size == 0:
        print("Error: Dataset is empty.")
        return
    sample_df = df.sample(n=sample_size, random_state=42)
    
    tp = 0
    fp = 0
    tn = 0
    fn = 0
    
    os.environ["USE_SEMANTIC_FILTER"] = "True"
    
    for index, row in tqdm(sample_df.iterrows(), total=sample_size, desc="Evaluating Pipeline"):
        text = row['text']
        try:
            labels = ast.literal_eval(row['labels'])
        except (KeyError, ValueError, SyntaxError) as e:
            print(f"Warning: Skipping row {index} due to parsing error in 'labels': {e}")
            continue
        
        # Ground truth
        has_pii = any(lbl != 'O' for lbl in labels)
        
        # Prediction
        _, _, action = pipeline.run(text)
        predicted_pii = action != "CLEAN"
        
        if has_pii and predicted_pii:
            tp += 1
        elif not has_pii and predicted_pii:
            fp += 1
        elif not has_pii and not predicted_pii:
            tn += 1
        elif has_pii and not predicted_pii:
            fn += 1

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    
    print("\n=== EVALUATION RESULTS ===")
    print(f"Total Rows: {total}")
    print(f"True Positives (TP): {tp}")
    print(f"False Positives (FP): {fp}")
    print(f"True Negatives (TN): {tn}")
    print(f"False Negatives (FN): {fn}")
    print(f"Accuracy:  {accuracy:.2%}")
    print(f"Recall:    {recall:.2%}")
    print(f"Precision: {precision:.2%}")

if __name__ == "__main__":
    evaluate()
