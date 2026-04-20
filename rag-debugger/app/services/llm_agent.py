from openai import OpenAI
import tiktoken
from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)
tokenizer = tiktoken.get_encoding("cl100k_base")

def generate_fix(context: str, model: str) -> str:
    """
    Submits the contextualized error to the LLM and requests a fix.
    Returns a unified git diff.
    """
    system_prompt = (
        "You are an expert Python debugging agent. "
        "You will be given the error stack trace and relevant code context. "
        "Your task is to identify the root cause and provide a fix. "
        "If a 'Primary File Location' is provided, focus your fix on that specific location. "
        "OUTPUT YOUR FIX USING A SEARCH/REPLACE BLOCK FORMAT. "
        "Do not use diff format. Follow this exact structure:\n"
        "<<<< path/to/file.py\n"
        "original lines (provide enough context to be UNIQUE in the file)\n"
        "====\n"
        "new replacement lines\n"
        ">>>>\n"
        "CRITICAL:\n"
        "1. Your SEARCH block must be UNIQUE to the specific block of code you wish to fix. "
        "2. If code is built dynamically (concatenations, f-strings), search only for the specific substring or unique line fragment containing the error. "
        "3. Provide the SMALLEST UNIQUE fragment possible to ensure successful matching. "
        "4. Fix only the core issue reported. Avoid broad refactorings. "
        "5. Do not wrap inside markdown blocks. Only use the <<<< / ==== / >>>> tokens."
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
        
        return output_str
    except Exception as e:
        print(f"LLM Error: {e}")
        return ""
