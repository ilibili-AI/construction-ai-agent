from groq import Groq
from config import GROQ_API_KEY, COMPANY_PROFILE
from prompts import get_system_prompt


class ConstructionAgent:
    def __init__(
        self,
        company_name: str = "",
        phone: str = "",
        email: str = "",
        services: str = "",
        area: str = "",
    ) -> None:
        self.company_name = company_name or COMPANY_PROFILE["company_name"]
        self.system_prompt = get_system_prompt(
            company_name=self.company_name,
            phone=phone or COMPANY_PROFILE["phone"],
            email=email or COMPANY_PROFILE["email"],
            services=services or COMPANY_PROFILE["services"],
            area=area or COMPANY_PROFILE["area"],
        )
        self.history = [{"role": "system", "content": self.system_prompt}]
        self._client = None

    def _get_client(self) -> Groq:
        if self._client is None:
            if not GROQ_API_KEY:
                raise ValueError("GROQ_API_KEY is not set")
            self._client = Groq(api_key=GROQ_API_KEY)
        return self._client

    def process_message(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        # حداکثر ۲۰ پیام در تاریخچه نگه داریم
        if len(self.history) > 21:
            system = self.history[0]
            self.history = [system] + self.history[-20:]

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.history,
                max_tokens=200,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
            if not reply:
                reply = "I apologize, I am having trouble. Please call our office directly."
        except Exception as e:
            print(f"[Agent] Error: {e}")
            reply = "I apologize, I am having trouble. Please call our office directly."

        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self.history = [{"role": "system", "content": self.system_prompt}]