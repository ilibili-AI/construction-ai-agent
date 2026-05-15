from groq import Groq
import os
from prompts import get_system_prompt
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class ConstructionAgent:
    def __init__(self, company_name="Our Company", phone="", email="", services="", area=""):
        self.company_name = company_name
        self.system_prompt = get_system_prompt(company_name, phone, email, services, area)
        self.history = [
            {"role": "system", "content": self.system_prompt}
        ]

    def process_message(self, user_message):
        try:
            self.history.append({"role": "user", "content": user_message})
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.history,
                max_tokens=150
            )
            reply = response.choices[0].message.content
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            print(f"Error: {e}")
            return "I apologize, I am having trouble. Please call our office directly."

    def reset(self):
        self.history = [
            {"role": "system", "content": self.system_prompt}
        ]