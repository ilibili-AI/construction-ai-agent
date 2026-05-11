from flask import Flask, request, jsonify, render_template_string
from agent import ConstructionAgent
from gtts import gTTS
import base64
import io

app = Flask(__name__)
agent = ConstructionAgent()

HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BuildAI — Construction Intelligence</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Segoe UI', sans-serif;
            min-height: 100vh;
            background: #f0f2f5;
            display: flex;
            flex-direction: column;
        }

        /* NAVBAR */
        nav {
            background: white;
            padding: 15px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 20px rgba(0,0,0,0.06);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            font-size: 1.3rem;
            font-weight: 800;
            color: #1a202c;
        }

        .logo span { color: #f7971e; }

        .nav-links {
            display: flex;
            gap: 30px;
            list-style: none;
        }

        .nav-links a {
            color: #718096;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: color 0.2s;
        }

        .nav-links a:hover { color: #f7971e; }

        .nav-badge {
            background: linear-gradient(135deg, #f7971e, #ffd200);
            color: white;
            padding: 8px 20px;
            border-radius: 25px;
            font-size: 0.85rem;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(247,151,30,0.3);
        }

        /* HERO */
        .hero {
            background: linear-gradient(135deg, #1a202c 0%, #2d3748 50%, #1a365d 100%);
            padding: 60px 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }

        .hero::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(ellipse at center, rgba(247,151,30,0.08) 0%, transparent 60%);
            animation: heroGlow 6s ease-in-out infinite;
        }

        @keyframes heroGlow {
            0%, 100% { transform: scale(1); opacity: 0.5; }
            50% { transform: scale(1.2); opacity: 1; }
        }

        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(247,151,30,0.15);
            border: 1px solid rgba(247,151,30,0.3);
            color: #ffd200;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 1px;
            margin-bottom: 20px;
        }

        .hero h1 {
            font-size: 2.8rem;
            font-weight: 900;
            color: white;
            margin-bottom: 15px;
            line-height: 1.2;
        }

        .hero h1 span {
            background: linear-gradient(90deg, #f7971e, #ffd200);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hero p {
            color: #a0aec0;
            font-size: 1rem;
            max-width: 500px;
            margin: 0 auto 30px;
            line-height: 1.7;
        }

        .hero-stats {
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 30px;
        }

        .hero-stat {
            text-align: center;
        }

        .hero-stat-num {
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(90deg, #f7971e, #ffd200);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hero-stat-label {
            color: #718096;
            font-size: 0.75rem;
            letter-spacing: 1px;
            text-transform: uppercase;
        }

        /* MAIN CONTENT */
        .main {
            flex: 1;
            display: flex;
            gap: 24px;
            padding: 30px 40px;
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
        }

        /* CHAT */
        .chat-section {
            flex: 1;
        }

        .chat-card {
            background: white;
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
            height: 580px;
            display: flex;
            flex-direction: column;
        }

        .chat-header {
            background: linear-gradient(135deg, #1a202c, #2d3748);
            padding: 18px 22px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .agent-avatar {
            width: 46px;
            height: 46px;
            background: linear-gradient(135deg, #f7971e, #ffd200);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
            position: relative;
        }

        .online-dot {
            position: absolute;
            bottom: 2px;
            right: 2px;
            width: 10px;
            height: 10px;
            background: #48bb78;
            border-radius: 50%;
            border: 2px solid #1a202c;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(72,187,120,0.4); }
            50% { box-shadow: 0 0 0 6px rgba(72,187,120,0); }
        }

        .agent-details h3 { color: white; font-size: 0.95rem; font-weight: 700; }
        .agent-details p { color: #a0aec0; font-size: 0.75rem; }

        .chat-body {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f7f8fa;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .chat-body::-webkit-scrollbar { width: 3px; }
        .chat-body::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 2px; }

        .message {
            display: flex;
            gap: 10px;
            animation: msgIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        @keyframes msgIn {
            from { opacity: 0; transform: translateY(10px) scale(0.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        .message.user { flex-direction: row-reverse; }

        .msg-av {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            flex-shrink: 0;
        }

        .sarah .msg-av { background: linear-gradient(135deg, #f7971e, #ffd200); }
        .user .msg-av { background: linear-gradient(135deg, #667eea, #764ba2); }

        .msg-bubble {
            max-width: 74%;
            padding: 11px 16px;
            border-radius: 18px;
            font-size: 0.87rem;
            line-height: 1.6;
        }

        .sarah .msg-bubble {
            background: white;
            color: #2d3748;
            border: 1px solid #e2e8f0;
            border-bottom-left-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }

        .user .msg-bubble {
            background: linear-gradient(135deg, #f7971e, #ffd200);
            color: white;
            border-bottom-right-radius: 4px;
            box-shadow: 0 4px 12px rgba(247,151,30,0.3);
        }

        .typing {
            display: flex;
            gap: 5px;
            padding: 12px 16px;
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 18px;
            border-bottom-left-radius: 4px;
            width: fit-content;
        }

        .typing span {
            width: 7px; height: 7px;
            background: #f7971e;
            border-radius: 50%;
            animation: bounce 1.2s infinite;
        }

        .typing span:nth-child(2) { animation-delay: 0.2s; }
        .typing span:nth-child(3) { animation-delay: 0.4s; }

        @keyframes bounce {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
            30% { transform: translateY(-7px); opacity: 1; }
        }

        .quick-btns {
            padding: 10px 16px;
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            background: white;
            border-top: 1px solid #f0f0f0;
        }

        .q-btn {
            padding: 6px 13px;
            background: #fff7ed;
            border: 1px solid #fed7aa;
            border-radius: 15px;
            font-size: 0.76rem;
            color: #c05621;
            cursor: pointer;
            transition: all 0.2s;
            font-weight: 500;
        }

        .q-btn:hover {
            background: #f7971e;
            color: white;
            border-color: #f7971e;
        }

        .chat-input {
            padding: 14px 18px;
            background: white;
            border-top: 1px solid #f0f0f0;
            display: flex;
            gap: 10px;
        }

        .chat-input input {
            flex: 1;
            background: #f7f8fa;
            border: 2px solid #e2e8f0;
            border-radius: 25px;
            padding: 11px 18px;
            font-size: 0.88rem;
            color: #2d3748;
            outline: none;
            transition: all 0.3s;
        }

        .chat-input input:focus {
            border-color: #f7971e;
            background: white;
            box-shadow: 0 0 0 3px rgba(247,151,30,0.1);
        }

        .chat-input input::placeholder { color: #a0aec0; }

        .send-btn {
            width: 46px; height: 46px;
            background: linear-gradient(135deg, #f7971e, #ffd200);
            border: none;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1rem;
            color: white;
            transition: all 0.3s;
            box-shadow: 0 4px 12px rgba(247,151,30,0.35);
            flex-shrink: 0;
        }

        .send-btn:hover { transform: scale(1.1); box-shadow: 0 6px 20px rgba(247,151,30,0.5); }
        .send-btn:active { transform: scale(0.95); }

        /* SIDEBAR */
        .sidebar {
            width: 280px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .side-card {
            background: white;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
        }

        .side-card h4 {
            font-size: 0.85rem;
            font-weight: 700;
            color: #1a202c;
            margin-bottom: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .feature-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid #f7f8fa;
        }

        .feature-item:last-child { border-bottom: none; }

        .feature-icon {
            width: 36px; height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            flex-shrink: 0;
        }

        .feature-text { font-size: 0.82rem; color: #4a5568; line-height: 1.4; }
        .feature-text strong { color: #1a202c; display: block; font-size: 0.85rem; }

        .stat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        .stat-box {
            background: #f7f8fa;
            border-radius: 12px;
            padding: 14px;
            text-align: center;
        }

        .stat-box .num {
            font-size: 1.4rem;
            font-weight: 800;
            color: #f7971e;
        }

        .stat-box .label {
            font-size: 0.7rem;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .testimonial {
            background: linear-gradient(135deg, #1a202c, #2d3748);
            border-radius: 16px;
            padding: 20px;
            color: white;
        }

        .testimonial p {
            font-size: 0.85rem;
            line-height: 1.6;
            color: #a0aec0;
            margin-bottom: 14px;
            font-style: italic;
        }

        .testimonial-author {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .t-avatar {
            width: 34px; height: 34px;
            background: linear-gradient(135deg, #f7971e, #ffd200);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
        }

        .t-name { font-size: 0.82rem; font-weight: 600; }
        .t-role { font-size: 0.72rem; color: #718096; }
    </style>
</head>
<body>

    <nav>
        <div class="logo">Build<span>AI</span></div>
        <ul class="nav-links">
            <li><a href="#">Home</a></li>
            <li><a href="#">Services</a></li>
            <li><a href="#">Projects</a></li>
            <li><a href="#">Contact</a></li>
        </ul>
        <div class="nav-badge">🟢 AI Online</div>
    </nav>

    <div class="hero">
        <div class="hero-badge">✨ POWERED BY ARTIFICIAL INTELLIGENCE</div>
        <h1>Your Smart<br><span>Construction Assistant</span></h1>
        <p>Get instant quotes, schedule meetings, and plan your project — all through a conversation with Sarah, our AI specialist.</p>
        <div class="hero-stats">
            <div class="hero-stat">
                <div class="hero-stat-num">500+</div>
                <div class="hero-stat-label">Projects Quoted</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-num">24/7</div>
                <div class="hero-stat-label">Available</div>
            </div>
            <div class="hero-stat">
                <div class="hero-stat-num">< 5s</div>
                <div class="hero-stat-label">Response Time</div>
            </div>
        </div>
    </div>

    <div class="main">
        <div class="chat-section">
            <div class="chat-card">
                <div class="chat-header">
                    <div class="agent-avatar">
                        👩‍💼
                        <div class="online-dot"></div>
                    </div>
                    <div class="agent-details">
                        <h3>Sarah — AI Construction Specialist</h3>
                        <p>Typically replies in under 5 seconds</p>
                    </div>
                </div>

                <div class="chat-body" id="chatBox">
                    <div class="message sarah">
                        <div class="msg-av">👩‍💼</div>
                        <div class="msg-bubble">Welcome! I'm Sarah, your AI construction specialist. I can help you with project quotes, planning, and scheduling. How can I assist you today?</div>
                    </div>
                </div>

                <div class="quick-btns">
                    <button class="q-btn" onclick="quickSend('I need a house quote')">🏠 House Quote</button>
                    <button class="q-btn" onclick="quickSend('Commercial building quote')">🏢 Commercial</button>
                    <button class="q-btn" onclick="quickSend('Schedule a meeting')">📅 Meeting</button>
                    <button class="q-btn" onclick="quickSend('Renovation quote')">🔨 Renovation</button>
                </div>

                <div class="chat-input">
                    <input type="text" id="userInput" placeholder="Ask Sarah anything..." onkeypress="if(event.key==='Enter') sendMessage()">
                    <button class="send-btn" onclick="sendMessage()">➤</button>
                </div>
            </div>
        </div>

        <div class="sidebar">
            <div class="side-card">
                <h4>What Sarah Can Do</h4>
                <div class="feature-item">
                    <div class="feature-icon" style="background:#fff7ed">💰</div>
                    <div class="feature-text"><strong>Instant Quotes</strong>Get rough estimates in seconds</div>
                </div>
                <div class="feature-item">
                    <div class="feature-icon" style="background:#f0fff4">📅</div>
                    <div class="feature-text"><strong>Schedule Meetings</strong>Book with our project managers</div>
                </div>
                <div class="feature-item">
                    <div class="feature-icon" style="background:#ebf8ff">📋</div>
                    <div class="feature-text"><strong>Project Planning</strong>Timeline and budget guidance</div>
                </div>
                <div class="feature-item">
                    <div class="feature-icon" style="background:#faf5ff">🔊</div>
                    <div class="feature-text"><strong>Voice Responses</strong>Sarah speaks to you directly</div>
                </div>
            </div>

            <div class="side-card">
                <h4>Our Track Record</h4>
                <div class="stat-grid">
                    <div class="stat-box"><div class="num">500+</div><div class="label">Projects</div></div>
                    <div class="stat-box"><div class="num">98%</div><div class="label">Satisfied</div></div>
                    <div class="stat-box"><div class="num">15yr</div><div class="label">Experience</div></div>
                    <div class="stat-box"><div class="num">24/7</div><div class="label">Support</div></div>
                </div>
            </div>

            <div class="testimonial">
                <p>"Sarah helped us get a quote and schedule a meeting in under 2 minutes. Incredibly efficient!"</p>
                <div class="testimonial-author">
                    <div class="t-avatar">👨‍💼</div>
                    <div>
                        <div class="t-name">Michael R.</div>
                        <div class="t-role">Real Estate Developer</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function addMessage(text, sender) {
            const box = document.getElementById('chatBox');
            const div = document.createElement('div');
            div.className = 'message ' + sender;
            const av = sender === 'user' ? '🧑' : '👩‍💼';
            div.innerHTML = `<div class="msg-av">${av}</div><div class="msg-bubble">${text}</div>`;
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
        }

        function showTyping() {
            const box = document.getElementById('chatBox');
            const div = document.createElement('div');
            div.className = 'message sarah';
            div.id = 'typing';
            div.innerHTML = `<div class="msg-av">👩‍💼</div><div class="typing"><span></span><span></span><span></span></div>`;
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
        }

        function removeTyping() {
            const t = document.getElementById('typing');
            if (t) t.remove();
        }

        function quickSend(text) {
            document.getElementById('userInput').value = text;
            sendMessage();
        }

        function sendMessage() {
            const input = document.getElementById('userInput');
            const text = input.value.trim();
            if (!text) return;
            addMessage(text, 'user');
            input.value = '';
            showTyping();

            fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: text})
            })
            .then(r => r.json())
            .then(data => {
                removeTyping();
                addMessage(data.response, 'sarah');
                const audio = new Audio('data:audio/mp3;base64,' + data.audio);
                audio.play();
            });
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    response = agent.process_message(user_message)
    tts = gTTS(text=response, lang='en')
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    audio_base64 = base64.b64encode(audio_buffer.read()).decode()
    return jsonify({'response': response, 'audio': audio_base64})

if __name__ == '__main__':
    app.run(debug=True, port=5000)