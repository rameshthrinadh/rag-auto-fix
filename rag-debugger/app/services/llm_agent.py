from openai import OpenAI
import tiktoken
from typing import Dict, Any, Optional
import json
import re

from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)
tokenizer = tiktoken.get_encoding("cl100k_base")

def generate_fix(context: str, model: str) -> Dict[str, Any]:
    """
    Submits the contextualized error to the LLM and requests a structured fix.
    Returns a dictionary with metadata and the fix payload.
    """
    system_prompt = (
        "You are an expert Python debugging agent. "
        "You must analyze the following error and provide a structured plan for repair.\n\n"
        "CORE RULE: 'IF YOU ARE NOT 100% SURE, DO NOT PROVIDE A FIX'.\n"
        "You are strictly prohibited from guessing or assuming column names, variable names, or business logic. "
        "All fixes must be based on direct evidence from the provided code context and stacktrace.\n\n"
        "Your response MUST strictly follow this exact format with these markers:\n"
        "[ROOT CAUSE]\n"
        "Briefly describe the bug origin.\n"
        "[EXPLANATION]\n"
        "Explain the fix logic and why it is safe. Include any doubts here.\n"
        "[CONFIDENCE]\n"
        "Integer 0-100. CRITICAL: If you are making ANY assumption or guess, your confidence MUST be below 50.\n"
        "[RISK]\n"
        "LOW, MEDIUM, or HIGH.\n"
        "[FIX]\n"
        "The Search/Replace blocks. If you are not confident, leave this section EMPTY.\n"
        "<<<< path/to/file.py\n"
        "original lines\n"
        "====\n"
        "replacement lines\n"
        ">>>>\n\n"
        "CRITICAL:\n"
        "1. NO GUESSING. If you have to assume a column name like 'quantity', you have FAILED the core rule.\n"
        "2. Your SEARCH block must be UNIQUE.\n"
        "3. DO NOT change function signatures.\n"
        "4. Fix only the core issue. Avoid broad refactorings.\n"
        "5. Do not wrap your response in markdown code blocks."
    )
    
    tokens_in = len(tokenizer.encode(system_prompt + "\n" + context))
    print(f"[{model}] LLM Input Tokens: {tokens_in}")
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            temperature=0.0
        )
        # Ensure output is clean
        output_str = response.choices[0].message.content.strip()
        
        # Still strip markdown if it randomly hallucinates codeblocks
        if output_str.startswith("```"):
            lines = output_str.split("\n")
            if len(lines) > 2 and lines[-1].strip() == "```":
                output_str = "\n".join(lines[1:-1])
            
        output_str = output_str.strip()
        
        tokens_out = response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else len(tokenizer.encode(output_str))
        print(f"[{model}] LLM Output Tokens: {tokens_out}")
        
        return parse_llm_response(output_str)
    except Exception as e:
        print(f"LLM Error: {e}")
        return {
            "root_cause": "Error communicating with LLM",
            "fix": "",
            "confidence": 0,
            "risk": "HIGH",
            "explanation": str(e)
        }

def parse_llm_response(raw_text: str) -> Dict[str, Any]:
    """
    Parses the structured text response from the LLM.
    """
    result = {
        "root_cause": "Unknown",
        "explanation": "No explanation provided.",
        "confidence": 0,
        "risk": "HIGH",
        "fix": ""
    }
    
    # Simple regex-based extraction for the sections
    rc_match = re.search(r"\[ROOT CAUSE\]\n(.*?)(?=\[|$)", raw_text, re.DOTALL)
    if rc_match: result["root_cause"] = rc_match.group(1).strip()
    
    exp_match = re.search(r"\[EXPLANATION\]\n(.*?)(?=\[|$)", raw_text, re.DOTALL)
    if exp_match: result["explanation"] = exp_match.group(1).strip()
    
    conf_match = re.search(r"\[CONFIDENCE\]\n(\d+)", raw_text)
    if conf_match: result["confidence"] = int(conf_match.group(1))
    
    risk_match = re.search(r"\[RISK\]\n(LOW|MEDIUM|HIGH)", raw_text, re.IGNORECASE)
    if risk_match: result["risk"] = risk_match.group(1).upper()
    
    fix_match = re.search(r"\[FIX\]\n(.*?)$", raw_text, re.DOTALL)
    if fix_match: result["fix"] = fix_match.group(1).strip()
    
    return result
