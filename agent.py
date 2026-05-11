from groq import Groq
import os
from prompts import SYSTEM_PROMPT
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class ConstructionAgent:
    def __init__(self):
        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def process_message(self, user_message):
        try:
            self.history.append({"role": "user", "content": user_message})
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.history,
                max_tokens=1024
            )
            reply = response.choices[0].message.content
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            print(f"Error: {e}")
            return "I apologize, I am having trouble."

    def reset(self):
        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]