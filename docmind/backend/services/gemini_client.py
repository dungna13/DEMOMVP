import os
import json
import google.generativeai as genai
from typing import AsyncGenerator, List, Dict

class GeminiClient:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

    async def stream_chat(self, system_prompt: str, history: List[Dict], message: str) -> AsyncGenerator[str, None]:
        # Formulate chat history for Gemini
        chat_history = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"] if msg["content"] else "[Empty]"
            chat_history.append({"role": role, "parts": [content]})
        
        # Start chat with system instruction
        model = genai.GenerativeModel(
            model_name='gemini-3.1-flash-lite-preview',
            system_instruction=system_prompt
        )
        
        try:
            chat = model.start_chat(history=chat_history)
            response = await chat.send_message_async(message, stream=True)
            
            async for chunk in response:
                try:
                    # Check for parts and text to avoid Safety Filter exceptions
                    if chunk.candidates and chunk.candidates[0].content.parts:
                        text = chunk.candidates[0].content.parts[0].text
                        if text:
                            yield text
                except (AttributeError, IndexError, ValueError) as e:
                    print(f"[GeminiClient] Stream chunk error (likely Safety Filter): {e}")
                    continue
        except Exception as e:
            print(f"[GeminiClient] Chat error: {e}")
            yield f"[Lỗi kết nối AI: {str(e)}]"

    async def generate_summary(self, system_prompt: str, context: str) -> AsyncGenerator[str, None]:
        model = genai.GenerativeModel(
            model_name='gemini-3.1-flash-lite-preview',
            system_instruction=system_prompt
        )
        try:
            response = await model.generate_content_async(context, stream=True)
            async for chunk in response:
                try:
                    if chunk.candidates and chunk.candidates[0].content.parts:
                        text = chunk.candidates[0].content.parts[0].text
                        if text:
                            yield text
                except (AttributeError, IndexError, ValueError):
                    continue
        except Exception as e:
            print(f"[GeminiClient] Summary error: {e}")
            yield f"[Lỗi tóm tắt: {str(e)}]"

    async def get_suggested_questions(self, context: str) -> List[str]:
        prompt = f"Based on the following document excerpts, suggest 4-6 diverse, insightful questions that a researcher might ask. Return only a JSON array of strings.\n\nCONTEXT:\n{context}"
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = await model.generate_content_async(prompt)
        try:
            # Simple cleanup for Gemini's markdown response
            text = response.text.strip()
            if text.startswith("```json"):
                text = text.split("```json")[1].split("```")[0].strip()
            elif text.startswith("```"):
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except:
            return ["Tell me more about the key findings.", "What are the limitations mentioned?", "Summarize the main arguments.", "What data was used?"]

gemini_client = GeminiClient()
