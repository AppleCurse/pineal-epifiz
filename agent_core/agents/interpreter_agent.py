"""Taktik kod yorumlayıcısı (Open Interpreter köprüsü) — VARSAYILAN OLARAK KAPALI.

``ENABLE_INTERPRETER=true`` iken yürütücü ajana eklenir; LLM'in ürettiği
Python/Shell kodunu Open Interpreter üzerinden koşturur ve yapılandırılmış
``InterpreterResult`` (prompt, code_blocks, output, status) döner.

Güvenlik: ``auto_run`` ZORLA False'tur — model kendi kodunu kendi başına
çalıştıramaz; her koşu insan onayı ister. Kimlik çözümlemesi gateway → env
sırasını izler. Paket kurulu değilse açık hata verir; kurulu ama bozuk bir
bağımlılık "paket yok" diye YANLIŞ etiketlenmez.

Test: ``tests/test_interpreter_agent.py``, ``tests/unit/test_intervention_safety.py``.
"""

from pydantic import BaseModel, ConfigDict
from typing import Dict, Any, List, Optional
import asyncio
import os

class InterpreterResult(BaseModel):
    prompt: str
    code_blocks: List[str] = []
    output: str = ""
    status: str = "success"  # "success", "error", "halted"
    error_message: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")

class InterpreterAgent:
    """
    Pineal-Heretic Tactical Code Interpreter Agent.
    Runs Open Interpreter to programmatically generate and execute Python/Shell code.
    """
    def __init__(self, llm_gateway=None):
        self.llm_gateway = llm_gateway

    def _setup_interpreter(self, api_key: str = None, model: str = None, auto_run: bool = False):
        try:
            from interpreter import interpreter
            
            interpreter.auto_run = False # Security Fix: Force auto_run to False to prevent arbitrary code execution
            interpreter.offline = False
            
            # Key configuration
            key = api_key or (self.llm_gateway.api_key if self.llm_gateway else os.getenv("OPENROUTER_API_KEY"))
            if key and not key.startswith("sk-or-v1-YOUR"):
                interpreter.llm.api_key = key
                interpreter.llm.api_base = "https://openrouter.ai/api/v1"
                # Default follows the 2026-09-02 matrix (retired ling-3.0-flash
                # is no longer the bare fallback). Override via `model=` arg.
                selected_model = model or "deepseek/deepseek-v4-flash"
                if not selected_model.startswith("openrouter/") and not ("local" in selected_model.lower() or "ollama" in selected_model.lower()):
                    selected_model = f"openrouter/{selected_model}"
                interpreter.llm.model = selected_model
            
            return interpreter
        except ModuleNotFoundError as exc:
            if exc.name == "interpreter":
                import logging
                logging.error("InterpreterAgent setup failed: open-interpreter is not installed")
                return None
            # An installed package with a broken transitive dependency must not
            # be mislabeled as an absent optional package.
            raise

    async def execute_task(self, prompt: str, api_key: str = None, model: str = None, auto_run: bool = False) -> InterpreterResult:
        """
        Executes a task prompt using Open Interpreter and returns structured execution results.
        """
        interpreter = self._setup_interpreter(api_key=api_key, model=model, auto_run=auto_run)
        
        if interpreter is None:
            # Fallback when open-interpreter package is not available
            return InterpreterResult(
                prompt=prompt,
                code_blocks=[],
                output="Open Interpreter kütüphanesi aktif değil.",
                status="error",
                error_message="open-interpreter package not installed"
            )
            
        try:
            # Run open-interpreter programmatically via asyncio thread pool
            def _run():
                messages = interpreter.chat(prompt, display=False)
                output_text = ""
                code_list = []
                for msg in messages:
                    if msg.get("type") == "code":
                        code_list.append(msg.get("code", ""))
                    if msg.get("type") == "output":
                        output_text += msg.get("output", "") + "\n"
                    elif msg.get("content"):
                        output_text += str(msg.get("content")) + "\n"
                return code_list, output_text.strip()

            code_blocks, output = await asyncio.to_thread(_run)
            return InterpreterResult(
                prompt=prompt,
                code_blocks=code_blocks,
                output=output or "İşlem tamamlandı.",
                status="success"
            )
        except Exception as e:
            return InterpreterResult(
                prompt=prompt,
                code_blocks=[],
                output="",
                status="error",
                error_message=str(e)
            )

    async def execute(self, input_data: Dict[str, Any], memory=None, llm_gateway=None) -> InterpreterResult:
        """PinealExecutor standart ajan arayüzü"""
        prompt = input_data.get("prompt") or input_data.get("task", "Sistem durumunu kontrol et.")
        gw = llm_gateway or self.llm_gateway
        key = gw.api_key if gw else None
        return await self.execute_task(prompt=prompt, api_key=key)
