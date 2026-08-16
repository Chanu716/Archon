from typing import List, Dict, Any
from archon.config import settings

def calculate_hotspot_risk(
    max_cyclomatic_complexity: int, 
    fan_in: int, 
    fan_out: int, 
    churn_count: int,
    repo_max_cc: int,
    repo_max_coupling: int,
    repo_max_churn: int
) -> tuple[float, str]:
    """
    Computes the Archon Risk Heuristic v1 score for a file.
    
    Returns:
        tuple[float, str]: (risk_score, risk_level)
    """
    # Prevent division by zero
    repo_max_cc = max(repo_max_cc, 1)
    repo_max_coupling = max(repo_max_coupling, 1)
    repo_max_churn = max(repo_max_churn, 1)
    
    total_coupling = fan_in + fan_out
    
    normalized_complexity = min(max_cyclomatic_complexity / repo_max_cc, 1.0)
    normalized_coupling = min(total_coupling / repo_max_coupling, 1.0)
    normalized_churn = min(churn_count / repo_max_churn, 1.0)
    
    risk_score = (
        (settings.RISK_WEIGHT_COMPLEXITY * normalized_complexity) +
        (settings.RISK_WEIGHT_COUPLING * normalized_coupling) +
        (settings.RISK_WEIGHT_CHURN * normalized_churn)
    )
    
    risk_score = round(risk_score, 4)
    
    if risk_score >= settings.RISK_THRESHOLD_HIGH:
        level = "CRITICAL" if risk_score >= 0.9 else "HIGH" # Extrapolating slightly from docs
    elif risk_score >= settings.RISK_THRESHOLD_MODERATE:
        level = "MODERATE"
    else:
        level = "LOW"
        
    return risk_score, level
