import os
import sqlite3
import webbrowser
import base64
import sys
import traceback
from threading import Timer
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load secret API key from .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: Please set your GEMINI_API_KEY in the .env file.")
    exit(1)

app = Flask(__name__)
client = genai.Client(api_key=api_key)

# =====================================================================
# DATABASE SETUP (BYPASSING WINDOWS FILE LOCKS)
# =====================================================================
def get_db():
    conn = sqlite3.connect("chat_history_v2.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS sessions 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      session_id INTEGER, 
                      role TEXT, 
                      content TEXT, 
                      file_data TEXT, 
                      mime_type TEXT)''')
        conn.commit()
        print("Fresh database 'chat_history_v2.db' initialized successfully with all columns!")

init_db()

# =====================================================================
# FRONTEND TEMPLATE (HTML, CSS, & JAVASCRIPT)
# =====================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chaitanya Chatbot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        body {
            background-color: #e0f2fe;
            color: #1e293b;
            height: 100vh;
        }
        .container {
            display: flex;
            height: 100vh;
        }
        .sidebar {
            width: 260px;
            background-color: #bae6fd;
            padding: 15px;
            display: flex;
            flex-direction: column;
            border-right: 1px solid #7dd3fc;
        }
        .btn-new-chat {
            background-color: #0284c7;
            color: #ffffff;
            border: none;
            padding: 12px;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            width: 100%;
            transition: background 0.2s;
        }
        .btn-new-chat:hover {
            background-color: #0369a1;
        }
        hr {
            border: 0;
            border-top: 1px solid #7dd3fc;
            margin: 15px 0;
        }
        .sessions-list {
            flex: 1;
            overflow-y: auto;
        }
        .session-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 5px;
            background-color: #f0f9ff;
            border: 1px solid #e0f2fe;
            color: #0369a1;
        }
        .session-item:hover, .session-item.active {
            background-color: #7dd3fc;
            color: #0c4a6e;
        }
        .session-title {
            font-size: 14px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 170px;
            font-weight: 500;
        }
        .btn-delete {
            background: none;
            border: none;
            cursor: pointer;
            font-size: 14px;
        }
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            position: relative;
        }
        header {
            padding: 20px;
            background-color: #bae6fd;
            border-bottom: 1px solid #7dd3fc;
            color: #0369a1;
        }
        .chat-messages {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 15px;
            position: relative;
            z-index: 2;
        }
        .welcome-center {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 24px;
            font-weight: 600;
            color: #0369a1;
            opacity: 0.6;
            text-align: center;
            pointer-events: none;
            z-index: 1;
            width: 100%;
        }
        .message {
            padding: 12px 16px;
            border-radius: 8px;
            max-width: 75%;
            white-space: pre-wrap;
            line-height: 1.5;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            z-index: 2;
        }
        .message.user {
            background-color: #0284c7;
            color: #ffffff;
            align-self: flex-end;
        }
        .message.assistant {
            background-color: #ffffff;
            color: #1e293b;
            align-self: flex-start;
            border: 1px solid #e2e8f0;
        }
        .attached-img {
            max-width: 100%;
            max-height: 200px;
            display: block;
            margin-top: 8px;
            border-radius: 4px;
        }
        
        /* BLACK THEMED CHAT INPUT AREA */
        .input-area {
            padding: 20px;
            background-color: #1e293b; 
            border-top: 1px solid #0f172a;
            z-index: 2;
        }
        #chat-form {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .file-upload-label {
            background-color: #334155; 
            color: #f8fafc;
            border: 1px solid #475569;
            border-radius: 6px;
            padding: 14px 18px;
            cursor: pointer;
            font-weight: bold;
            font-size: 18px;
            transition: background 0.2s;
            display: inline-block;
        }
        .file-upload-label:hover {
            background-color: #475569;
        }
        #file-input {
            display: none;
        }
        #user-input {
            flex: 1;
            padding: 14px;
            background-color: #0f172a; 
            border: 1px solid #334155;
            border-radius: 6px;
            color: #f8fafc; 
            outline: none;
        }
        #user-input::placeholder {
            color: #64748b; 
        }
        #send-btn {
            background-color: #10b981;
            color: #ffffff;
            border: none;
            padding: 14px 24px;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.2s;
        }
        #send-btn:hover {
            background-color: #059669;
        }
        #file-preview-banner {
            font-size: 13px;
            color: #34d399;
            margin-bottom: 5px;
            padding-left: 55px;
            display: none;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <button id="new-chat-btn" class="btn-new-chat">➕ New Conversation</button>
            <hr>
            <div id="sessions-list" class="sessions-list"></div>
        </div>

        <div class="chat-area">
            <header>
                <h2>🤖 Chaitanya Chatbot</h2>
            </header>
            
            <div id="welcome-message" class="welcome-center">What's going on today?</div>
            
            <div id="chat-messages" class="chat-messages"></div>

            <div class="input-area">
                <div id="file-preview-banner">📎 File selected ready to upload</div>
                <form id="chat-form">
                    <label for="file-input" class="file-upload-label">➕</label>
                    <input type="file" id="file-input" accept="image/*,application/pdf,text/*">
                    
                    <input type="text" id="user-input" placeholder="Type your message here..." autocomplete="off" required>
                    <button type="submit" id="send-btn">Send</button>
                </form>
            </div>
        </div>
    </div>

    <script>
        let currentSessionId = null;
        let selectedFileBase64 = null;
        let selectedFileMime = null;

        document.addEventListener("DOMContentLoaded", () => {
            loadSessions();
            document.getElementById("new-chat-btn").addEventListener("click", createNewChat);
            document.getElementById("chat-form").addEventListener("submit", handleSendMessage);
            document.getElementById("file-input").addEventListener("change", handleFileSelection);
        });

        function handleFileSelection(e) {
            const file = e.target.files[0];
            if (!file) return;
            
            selectedFileMime = file.type;
            const reader = new FileReader();
            reader.onload = function(event) {
                selectedFileBase64 = event.target.result.split(',')[1];
                document.getElementById("file-preview-banner").style.display = "block";
                document.getElementById("file-preview-banner").textContent = `📎 Ready: ${file.name}`;
                document.getElementById("welcome-message").style.display = "none";
            };
            reader.readAsDataURL(file);
        }

        async function loadSessions() {
            const response = await fetch("/api/sessions");
            const sessions = await response.json();
            
            const listContainer = document.getElementById("sessions-list");
            listContainer.innerHTML = "";
            
            if (sessions.length === 0) {
                await createNewChat();
                return;
            }
            
            if (!currentSessionId) {
                currentSessionId = sessions[0].id;
            }
            
            sessions.forEach(session => {
                const item = document.createElement("div");
                item.className = `session-item ${session.id === currentSessionId ? 'active' : ''}`;
                
                item.innerHTML = `
                    <span class="session-title">${session.title}</span>
                    <button class="btn-delete" onclick="deleteChat(event, ${session.id})">🗑️</button>
                `;
                
                item.addEventListener("click", () => selectChat(session.id));
                listContainer.appendChild(item);
            });
            
            if (currentSessionId) {
                loadMessages(currentSessionId);
            }
        }

        async function createNewChat() {
            const response = await fetch("/api/sessions", { method: "POST" });
            const data = await response.json();
            currentSessionId = data.session_id;
            await loadSessions();
        }

        async function selectChat(sessionId) {
            currentSessionId = sessionId;
            await loadSessions();
        }

        async function deleteChat(event, sessionId) {
            event.stopPropagation();
            await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
            if (currentSessionId === sessionId) {
                currentSessionId = null;
            }
            await loadSessions();
        }

        async function loadMessages(sessionId) {
            const response = await fetch(`/api/messages/${sessionId}`);
            const messages = await response.json();
            
            const chatContainer = document.getElementById("chat-messages");
            chatContainer.innerHTML = "";
            
            if (messages.length === 0) {
                document.getElementById("welcome-message").style.display = "block";
            } else {
                document.getElementById("welcome-message").style.display = "none";
            }
            
            messages.forEach(msg => {
                appendMessage(msg.role, msg.content, msg.file_data, msg.mime_type);
            });
        }

        function appendMessage(role, content, fileData=null, mimeType=null) {
            document.getElementById("welcome-message").style.display = "none";
            
            const chatContainer = document.getElementById("chat-messages");
            const msgDiv = document.createElement("div");
            msgDiv.className = `message ${role}`;
            msgDiv.textContent = content;
            
            if (fileData && mimeType && mimeType.startsWith("image/")) {
                const img = document.createElement("img");
                img.src = `data:${mimeType};base64,${fileData}`;
                img.className = "attached-img";
                msgDiv.appendChild(img);
            } else if (fileData && mimeType) {
                const docLabel = document.createElement("div");
                docLabel.style.fontSize = "11px";
                docLabel.style.marginTop = "5px";
                docLabel.style.color = "#64748b";
                docLabel.textContent = "📄 Document attached analyzed by AI";
                msgDiv.appendChild(docLabel);
            }
            
            chatContainer.appendChild(msgDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        async function handleSendMessage(e) {
            e.preventDefault();
            const inputEl = document.getElementById("user-input");
            const message = inputEl.value.trim();
            if (!message || !currentSessionId) return;
            
            appendMessage("user", message, selectedFileBase64, selectedFileMime);
            inputEl.value = "";
            
            const postData = {
                session_id: currentSessionId,
                message: message,
                file_data: selectedFileBase64,
                mime_type: selectedFileMime
            };
            
            selectedFileBase64 = null;
            selectedFileMime = null;
            document.getElementById("file-input").value = "";
            document.getElementById("file-preview-banner").style.display = "none";
            
            appendMessage("assistant", "Thinking...");
            
            try {
                const response = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(postData)
                });
                
                const data = await response.json();
                
                const messages = document.querySelectorAll(".message.assistant");
                if(messages.length > 0) messages[messages.length - 1].remove();
                
                appendMessage("assistant", data.reply);
            } catch (err) {
                const messages = document.querySelectorAll(".message.assistant");
                if(messages.length > 0) messages[messages.length - 1].remove();
                appendMessage("assistant", "Error: Server connection lost. Look at your Python terminal.");
            }
            await loadSessions();
        }
    </script>
</body>
</html>
"""

# =====================================================================
# FLASK BACKEND ROUTES
# =====================================================================

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/sessions', methods=['GET', 'POST'])
def handle_sessions():
    conn = get_db()
    if request.method == 'POST':
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions (title) VALUES (?)", ("New Conversation",))
        conn.commit()
        session_id = cursor.lastrowid
        return jsonify({"session_id": session_id})
    else:
        sessions = conn.execute("SELECT id, title FROM sessions ORDER BY id DESC").fetchall()
        return jsonify([dict(row) for row in sessions])

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
    return jsonify({"status": "success"})

@app.route('/api/messages/<int:session_id>', methods=['GET'])
def get_messages(session_id):
    conn = get_db()
    messages = conn.execute("SELECT role, content, file_data, mime_type FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)).fetchall()
    return jsonify([dict(row) for row in messages])

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        session_id = data.get("session_id")
        user_message = data.get("message")
        file_data = data.get("file_data")   
        mime_type = data.get("mime_type")   
        
        conn = get_db()
        
        user_msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,)).fetchone()[0]
        if user_msg_count == 0:
            title = user_message[:25] + "..." if len(user_message) > 25 else user_message
            conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        
        conn.execute("INSERT INTO messages (session_id, role, content, file_data, mime_type) VALUES (?, 'user', ?, ?, ?)", 
                     (session_id, user_message, file_data, mime_type))
        conn.commit()
        
        history_rows = conn.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)).fetchall()
        contents_history = []
        
        for row in history_rows:
            role = "user" if row["role"] == "user" else "model"
            text_val = row["content"] if row["content"] else " "
            contents_history.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text_val)])
            )
            
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents_history
            )
            ai_reply = response.text
        except Exception as api_err:
            print(traceback.format_exc())
            ai_reply = f"System Error: Failed to pull response from Gemini API. Context: {str(api_err)}"
            
        conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)", (session_id, ai_reply))
        conn.commit()
        
        return jsonify({"reply": ai_reply})

    except Exception as server_err:
        print(traceback.format_exc(), file=sys.stderr)
        return jsonify({"reply": f"Internal Server Code Crash Alert: {str(server_err)}"})

def open_browser():
    webbrowser.open_new("http://127.0.0.1:8500/")

if __name__ == '__main__':
    Timer(1, open_browser).start()
    app.run(debug=False, port=8500)