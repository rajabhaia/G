# -*- coding: utf-8 -*-
#!/usr/bin/env python3
""" Carnal Live Mic Userbot - Ultimate Edition with Advanced Security """

import asyncio
import os
import platform
import signal
import subprocess
import stat
import json
import re
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set

try:
    from pyrogram import Client, filters
    from pyrogram.types import Message, User
    from pyrogram.errors import FloodWait, UserNotParticipant
except ImportError as e:
    print(f"ImportError: {e}")
    print("Please ensure pyrogram is installed: pip3 install pyrogram==2.0.106")
    exit(1)

# Try importing pytgcalls components
USE_GROUP_CALL_FACTORY = False
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import AudioPiped
    from pytgcalls.types.input_stream import AudioParameters
except ImportError:
    try:
        from pytgcalls import GroupCallFactory
        USE_GROUP_CALL_FACTORY = True
    except ImportError as e:
        print(f"ImportError: {e}")
        print("Please ensure pytgcalls is installed: pip3 install pytgcalls==2.1.0")
        print("If pytgcalls fails, try: pip3 install --force-reinstall pytgcalls==2.1.0")
        exit(1)

# ====================== CONFIG ==========================
API_ID = 27494996
API_HASH = "791274de917e999ebab112e60f3a163e"
SESSION_NAME = "carnal_bot"
SESSION_STRING = "BQGjilQAk2YfqjsMhrMKSeOlImREH0a1wx-x1FAOyO-8EcUSqiXqEFUXtshDGLdVeUDYheKHiNzf0Rl_mUkyzBQSGU-G1Pme0jEpJx37VA4XOapQlGv4qD7dqXw44vC7m5hzoT2esgTJH4TkOwnY3XSCoxttoZYk881AyV5grFbX43s6buAgbiCLdk1nRCJMgKQkH6fT8v9bZVFsyiK0fNl40Cfmc8QKVxjOBrP73Iogq2OPWTrwUQw8ouGNhvjcC68NZHulZpdhUC1HqKu3kJrOQ-u3q4Wk9o407pJLQ2mEnl0pRTH3pm1GVMw5vfWsqD6LFlv7sikt1-1VdbpCv7AnX6SRsQAAAAHq0DIpAA"

# ADMIN CONFIGURATION
ADMIN_IDS = [8234480169]  # Replace with your User ID
ALLOWED_GROUP_IDS = [-1002959335958]  # Replace with allowed Group ID

# SECURITY CONFIG
MAX_WARNINGS = 3
SPAM_TIME_WINDOW = 10  # seconds
MAX_MESSAGES_IN_WINDOW = 5
BLOCK_DURATION = 3600  # 1 hour in seconds
AUTO_DELETE_DELAY = 60  # seconds

# BAD WORDS LIST (Hindi/English profanity)
BAD_WORDS = [
    "madarchod", "bhosdike", "chutiya", "lund", "gaand", "behenchod", "maa ki chut",
    "bhenchod", "lauda", "lavde", "chod", "chut", "fuck", "asshole", "bitch", "dick",
    "pussy", "shit", "cunt", "motherfucker", "bullshit", "bastard", "dickhead", "piss",
    "ass", "faggot", "nigger", "whore", "slut", "douche", "fuckyou", "fuckoff"
]

# PHONE NUMBER REGEX PATTERNS
PHONE_PATTERNS = [
    r'\b\d{10}\b',  # 10-digit numbers
    r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # US format
    r'\b\d{5}[-.\s]?\d{5}\b',  # 5+5 format
    r'\b\d{4}[-.\s]?\d{3}[-.\s]?\d{3}\b',  # 4+3+3 format
]

# OTP REGEX PATTERNS
OTP_PATTERNS = [
    r'\b\d{4}\b',  # 4-digit OTP
    r'\b\d{6}\b',  # 6-digit OTP
    r'OTP.*\d{4,6}',  # OTP followed by digits
    r'verification.*\d{4,6}',  # verification code
]

# FIFO/pipe file paths
FIFO_PATH = "carnal_live.wav" if platform.system() == "Windows" else "/tmp/carnal_live.wav"
SONG_FIFO_PATH = "carnal_song.wav" if platform.system() == "Windows" else "/tmp/carnal_song.wav"

# Input device for Linux
LINUX_PULSE_SOURCE = "default"

# Default audio settings
DEFAULT_AUDIO_SETTINGS = {
    "sample_rate": 48000,
    "channels": 1,
    "codec": "pcm_s16le",
    "bass_gain": 8,
    "bass_frequency": 120,
    "compressor_threshold": -18,
    "compressor_ratio": 4,
    "compressor_makeup": 4,
    "reverb_level": 0.6,
    "reverb_delay": 0.5,
    "reverb_decay": 30,
    "pitch_factor": 0.95,
    "tempo_factor": 1.04,
    "volume_boost": 2.0,
    "loudness_gain": 12,
    "echo_level": 0.6
}

# Unlimited settings for all modes
UNLIMITED_SETTINGS = {
    "volume_boost": 10.0,
    "loudness_gain": 30,
    "echo_level": 0.95,
    "reverb_level": 0.95,
    "reverb_decay": 100,
    "bass_gain": 25,
    "compressor_makeup": 15,
    "compressor_threshold": -30,
    "compressor_ratio": 8,
    "reverb_delay": 0.8,
    "pitch_factor": 0.90,
    "tempo_factor": 1.08
}

# Carnal Mode Preset
CARNAL_MODE_PRESET = {
    "bass_gain": 20,
    "bass_frequency": 100,
    "compressor_threshold": -30,
    "compressor_ratio": 8,
    "compressor_makeup": 10,
    "reverb_level": 0.9,
    "reverb_delay": 0.8,
    "reverb_decay": 50,
    "pitch_factor": 0.90,
    "tempo_factor": 1.08,
    "volume_boost": 5.0,
    "loudness_gain": 20,
    "echo_level": 0.85
}

# Configuration file paths
CONFIG_FILE = "carnal_config.json"
SECURITY_FILE = "security_data.json"

# ========================================================

@dataclass
class FFmpegProcess:
    proc: Optional[subprocess.Popen] = None
    process_type: str = "mic"

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.proc and self.is_running():
            try:
                if platform.system() == "Windows":
                    os.kill(self.proc.pid, signal.CTRL_BREAK_EVENT)
                else:
                    self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except Exception as e:
                print(f"Error stopping FFmpeg: {e}")
            finally:
                self.proc = None

class SecuritySystem:
    def __init__(self):
        self.user_warnings: Dict[int, int] = {}  # user_id: warning_count
        self.user_messages: Dict[int, List[float]] = {}  # user_id: list of message timestamps
        self.blocked_users: Dict[int, float] = {}  # user_id: unblock_time
        self.load_security_data()
    
    def load_security_data(self):
        try:
            if os.path.exists(SECURITY_FILE):
                with open(SECURITY_FILE, 'r') as f:
                    data = json.load(f)
                    self.user_warnings = data.get("user_warnings", {})
                    self.blocked_users = data.get("blocked_users", {})
        except Exception as e:
            print(f"Error loading security data: {e}")
    
    def save_security_data(self):
        try:
            data = {
                "user_warnings": self.user_warnings,
                "blocked_users": self.blocked_users
            }
            with open(SECURITY_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving security data: {e}")
    
    def check_spam(self, user_id: int) -> bool:
        now = time.time()
        if user_id not in self.user_messages:
            self.user_messages[user_id] = []
        
        # Clean old messages
        self.user_messages[user_id] = [t for t in self.user_messages[user_id] if now - t < SPAM_TIME_WINDOW]
        
        # Add current message timestamp
        self.user_messages[user_id].append(now)
        
        # Check if user is spamming
        if len(self.user_messages[user_id]) > MAX_MESSAGES_IN_WINDOW:
            return True
        return False
    
    def add_warning(self, user_id: int) -> int:
        if user_id not in self.user_warnings:
            self.user_warnings[user_id] = 0
        self.user_warnings[user_id] += 1
        self.save_security_data()
        return self.user_warnings[user_id]
    
    def block_user(self, user_id: int, duration: int = BLOCK_DURATION):
        unblock_time = time.time() + duration
        self.blocked_users[user_id] = unblock_time
        self.save_security_data()
    
    def is_blocked(self, user_id: int) -> bool:
        if user_id in self.blocked_users:
            if time.time() < self.blocked_users[user_id]:
                return True
            else:
                # Remove expired block
                del self.blocked_users[user_id]
                self.save_security_data()
        return False
    
    def get_warnings(self, user_id: int) -> int:
        return self.user_warnings.get(user_id, 0)
    
    def reset_warnings(self, user_id: int):
        if user_id in self.user_warnings:
            del self.user_warnings[user_id]
            self.save_security_data()

class AudioSettings:
    def __init__(self):
        self.settings = DEFAULT_AUDIO_SETTINGS.copy()
        self.load_settings()
    
    def load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    loaded_settings = json.load(f)
                    self.settings.update(loaded_settings)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def save_settings(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def set_unlimited_mode(self, mode: str):
        """Apply unlimited settings for the specified mode"""
        if mode in ["volume", "echo", "loudness", "bass", "reverb", "compressor", "pitch", "tempo"]:
            self.settings.update(UNLIMITED_SETTINGS)
            self.save_settings()
    
    def set_carnal_mode(self):
        self.settings.update(CARNAL_MODE_PRESET)
        self.save_settings()
    
    def get_filter_chain(self, for_song: bool = False) -> str:
        if for_song:
            return (
                f"volume={self.settings['volume_boost'] * 0.7},"
                f"bass=g={self.settings['bass_gain'] * 0.8}:f={self.settings['bass_frequency']}:t=q:w=1.2,"
                f"acompressor=threshold={self.settings['compressor_threshold']}dB:"
                f"ratio={self.settings['compressor_ratio']}:attack=5:release=1000:"
                f"makeup={self.settings['compressor_makeup'] * 0.8},"
                f"aecho={self.settings['echo_level'] * 0.7}:{self.settings['reverb_delay']}:"
                f"{self.settings['reverb_decay'] * 0.7}:0.3"
            )
        
        return (
            f"asetrate={self.settings['sample_rate']}*{self.settings['pitch_factor']},"
            f"aresample={self.settings['sample_rate']},"
            f"atempo={self.settings['tempo_factor']},"
            f"bass=g={self.settings['bass_gain']}:f={self.settings['bass_frequency']}:t=q:w=1.2,"
            f"acompressor=threshold={self.settings['compressor_threshold']}dB:"
            f"ratio={self.settings['compressor_ratio']}:attack=5:release=1000:"
            f"makeup={self.settings['compressor_makeup']},"
            f"aecho={self.settings['echo_level']}:{self.settings['reverb_delay']}:"
            f"{self.settings['reverb_decay']}:0.3,"
            f"volume={self.settings['volume_boost']},"
            f"loudnorm=I=-5:TP=-1.5:LRA=11"
        )
    
    def get_audio_args(self) -> Dict[str, Any]:
        return {
            "ar": self.settings["sample_rate"],
            "ac": self.settings["channels"],
            "codec": self.settings["codec"],
        }

# Global instances
ff_mic = FFmpegProcess(process_type="mic")
ff_song = FFmpegProcess(process_type="song")
audio_settings = AudioSettings()
security_system = SecuritySystem()
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# Initialize pytgcalls
if USE_GROUP_CALL_FACTORY:
    print("Using GroupCallFactory for pytgcalls...")
    # FIX: The MTPROTO_CLIENT_TYPE_PYROGRAM attribute is no longer needed
    call = GroupCallFactory(app).get_group_call()
else:
    print("Using PyTgCalls...")
    call = PyTgCalls(app)

# Store active chats
active_chats: Set[int] = set()

# ================== UTILITY FUNCTIONS ==================

def ensure_fifo(path: str):
    if platform.system() == "Windows":
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        open(path, "wb").close()
    else:
        if os.path.exists(path):
            if not stat.S_ISFIFO(os.stat(path).st_mode):
                os.remove(path)
        if not os.path.exists(path):
            os.mkfifo(path)

def build_ffmpeg_cmd(input_source: str, for_song: bool = False) -> List[str]:
    """Build FFmpeg command for audio processing"""
    audio_args = audio_settings.get_audio_args()
    filter_chain = audio_settings.get_filter_chain(for_song)
    output_path = SONG_FIFO_PATH if for_song else FIFO_PATH

    out_args = [
        "-ac", str(audio_args["ac"]),
        "-ar", str(audio_args["ar"]),
        "-acodec", audio_args["codec"],
        "-f", "wav",
        output_path,
    ]

    if for_song:
        return [
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning",
            "-y",
            "-i", input_source,
            "-vn",
            "-af", filter_chain,
            *out_args,
        ]

    # For Linux PulseAudio
    return [
        "ffmpeg",
        "-hide_banner", "-loglevel", "warning",
        "-y",
        "-f", "pulse",
        "-i", LINUX_PULSE_SOURCE,
        "-vn",
        "-af", filter_chain,
        *out_args,
    ]

def command_exists(cmd: str) -> bool:
    """Check if a command exists in the system PATH"""
    from shutil import which
    return which(cmd) is not None

def check_node_version() -> bool:
    """Check if Node.js is installed and meets the minimum version requirement (15.0.0)"""
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
        version = result.stdout.strip().lstrip("v")
        major_version = int(version.split(".")[0])
        return major_version >= 15
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Node.js check failed: {e}")
        return False

# ================== NOTIFICATION FUNCTIONS ==================

async def send_notification(text: str):
    """Send notification to all admin users"""
    for admin_id in ADMIN_IDS:
        try:
            await app.send_message(admin_id, text)
        except Exception as e:
            print(f"Failed to send notification to {admin_id}: {e}")

async def log_event(event_type: str, details: str):
    """Log events with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"🕒 **{timestamp}** | **{event_type}**\n{details}"
    print(log_message)
    await send_notification(log_message)

# ================== SECURITY FUNCTIONS ==================

def contains_bad_words(text: str) -> bool:
    """Check if text contains bad words"""
    text_lower = text.lower()
    for word in BAD_WORDS:
        if word in text_lower:
            return True
    return False

def contains_phone_number(text: str) -> bool:
    """Check if text contains phone numbers"""
    for pattern in PHONE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

def contains_otp(text: str) -> bool:
    """Check if text contains OTP codes"""
    for pattern in OTP_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

async def delete_message_with_delay(message: Message, delay: int = AUTO_DELETE_DELAY):
    """Delete message after delay"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

async def warn_user(message: Message, reason: str):
    """Warn user and take appropriate action"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Add warning
    warning_count = security_system.add_warning(user_id)
    
    # Send warning message
    warn_msg = await message.reply_text(
        f"⚠️ **Warning {warning_count}/{MAX_WARNINGS}**\n"
        f"User: {message.from_user.mention}\n"
        f"Reason: {reason}\n\n"
        f"Next violation will result in a ban!"
    )
    
    # Log the warning
    await log_event("SECURITY_WARNING", 
                   f"User: {message.from_user.mention}\n"
                   f"ID: {user_id}\n"
                   f"Reason: {reason}\n"
                   f"Warnings: {warning_count}/{MAX_WARNINGS}")
    
    # Delete both messages after delay
    asyncio.create_task(delete_message_with_delay(message))
    asyncio.create_task(delete_message_with_delay(warn_msg))
    
    # Block user if max warnings reached
    if warning_count >= MAX_WARNINGS:
        security_system.block_user(user_id)
        ban_msg = await message.reply_text(
            f"🚫 **User Banned**\n"
            f"User: {message.from_user.mention}\n"
            f"Reason: Too many warnings\n"
            f"Duration: 1 hour"
        )
        asyncio.create_task(delete_message_with_delay(ban_msg))
        
        # Log the ban
        await log_event("USER_BANNED", 
                       f"User: {message.from_user.mention}\n"
                       f"ID: {user_id}\n"
                       f"Reason: Reached max warnings")

async def handle_violation(message: Message, violation_type: str):
    """Handle security violations"""
    user_id = message.from_user.id
    
    # Don't take action against admins
    if await is_admin(user_id, message.chat.id):
        return
    
    # Check if user is already blocked
    if security_system.is_blocked(user_id):
        try:
            await message.delete()
        except Exception:
            pass
        return
    
    reasons = {
        "spam": "Spamming messages",
        "bad_words": "Using inappropriate language",
        "phone": "Sharing phone numbers",
        "otp": "Sharing OTP/sensitive codes"
    }
    
    reason = reasons.get(violation_type, "Violating group rules")
    await warn_user(message, reason)

# ================== AUTHENTICATION FUNCTIONS ==================

async def is_admin(user_id: int, chat_id: int) -> bool:
    """Check if user is admin"""
    if user_id in ADMIN_IDS:
        return True
    
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

async def is_allowed(user_id: int, chat_id: int) -> bool:
    """Check if user is allowed to use commands"""
    if security_system.is_blocked(user_id):
        return False
    if chat_id == user_id:
        return True
    if user_id in ADMIN_IDS:
        return True
    if chat_id in ALLOWED_GROUP_IDS:
        return True
    return False

# ================== STREAMING FUNCTIONS ==================

async def start_stream(chat_id: int, for_song: bool = False, song_path: str = None):
    """Start audio stream with FFmpeg and PyTgCalls/GroupCallFactory"""
    if not command_exists("ffmpeg"):
        raise Exception("FFmpeg is not installed or not found in PATH")
    
    output_path = SONG_FIFO_PATH if for_song else FIFO_PATH
    ensure_fifo(output_path)

    ff_process = ff_song if for_song else ff_mic
    
    if not ff_process.is_running():
        input_source = song_path if for_song else "default"
        cmd = build_ffmpeg_cmd(input_source, for_song)
        try:
            ff_process.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(2)
        except Exception as e:
            raise Exception(f"Failed to start FFmpeg: {e}")

    try:
        stream_params = None
        if not USE_GROUP_CALL_FACTORY:
            stream_params = AudioPiped(
                output_path,
                AudioParameters(
                    bitrate=48000,
                    channels=audio_settings.settings["channels"]
                )
            )
            await call.join_group_call(chat_id, stream_params)
        else:
            stream_params = output_path
            await call.start(chat_id)
            await call.play(stream_params)
        active_chats.add(chat_id)
        # Send join notification to group
        if chat_id in ALLOWED_GROUP_IDS:
            try:
                await app.send_message(chat_id, "🎤 **Carnal Bot** has joined the voice chat! 🚀")
                await log_event("VOICE_CHAT_JOINED", f"Chat ID: {chat_id}")
            except Exception as e:
                print(f"Error sending join notification: {e}")
    except Exception as e:
        ff_process.stop()
        raise Exception(f"Failed to join voice call: {e}")

async def stop_stream(chat_id: int):
    """Stop audio stream and clean up"""
    try:
        if chat_id in active_chats:
            if USE_GROUP_CALL_FACTORY:
                await call.stop()
            else:
                await call.leave_group_call(chat_id)
            active_chats.remove(chat_id)
            # Send leave notification to group
            if chat_id in ALLOWED_GROUP_IDS:
                try:
                    await app.send_message(chat_id, "🔴 **Carnal Bot** has left the voice chat! ❌")
                    await log_event("VOICE_CHAT_LEFT", f"Chat ID: {chat_id}")
                except Exception as e:
                    print(f"Error sending leave notification: {e}")
    except Exception as e:
        print(f"Error leaving call: {e}")
    
    ff_mic.stop()
    ff_song.stop()

async def download_audio(message: Message) -> str:
    """Download audio from message and return file path"""
    target_msg = message.reply_to_message if message.reply_to_message else message
    
    if target_msg.audio:
        file_id = target_msg.audio.file_id
    elif target_msg.voice:
        file_id = target_msg.voice.file_id
    elif target_msg.video:
        file_id = target_msg.video.file_id
    elif target_msg.document:
        file_id = target_msg.document.file_id
    else:
        raise Exception("No audio or video found to play")
    
    download_path = await target_msg.download()
    return download_path

# ================== SECURITY FILTERS ==================

async def security_filter(_, __, message: Message):
    """Filter to check for security violations"""
    # Skip if no text or from admin
    if not message.text or await is_admin(message.from_user.id, message.chat.id):
        return False
    
    text = message.text.lower()
    
    # Check for spam
    if security_system.check_spam(message.from_user.id):
        return True
    
    # Check for bad words
    if contains_bad_words(text):
        return True
    
    # Check for phone numbers
    if contains_phone_number(text):
        return True
    
    # Check for OTP codes
    if contains_otp(text):
        return True
    
    return False

security_check = filters.create(security_filter)

async def allowed_filter(_, __, message: Message):
    """Filter to check if user is allowed to use commands"""
    user_id = message.from_user.id if message.from_user else 0
    return await is_allowed(user_id, message.chat.id)

allowed_only = filters.create(allowed_filter)

# ================== SECURITY HANDLERS ==================

@app.on_message(filters.text & security_check)
async def handle_security_violation(client, message: Message):
    """Handle security violations"""
    text = message.text.lower()
    
    if security_system.check_spam(message.from_user.id):
        await handle_violation(message, "spam")
    elif contains_bad_words(text):
        await handle_violation(message, "bad_words")
    elif contains_phone_number(text):
        await handle_violation(message, "phone")
    elif contains_otp(text):
        await handle_violation(message, "otp")

# ================== COMMANDS ==================

@app.on_message(filters.command(["help", "start"]) & allowed_only)
async def cmd_help(client, message: Message):
    """Display all available commands with descriptions"""
    help_text = """
🤖 **Carnal Live Mic Userbot - Help Menu**

🎤 **Voice Chat Commands:**
• `/activevc` - Show all active voice chats
• `/carnal` - Activate ULTIMATE CARNAL MODE with max settings
• `/off` or `/stopfx` - Stop the voice chat stream
• `/on` or `/startfx` - Start the live mic stream
• `/play` - Play audio/video file (reply to audio/video)

⚙️ **Audio Effect Commands:**
• `/bass unlimited` - Max bass boost
• `/compressor unlimited` - Max compressor settings
• `/echo unlimited` - Max echo effect
• `/loudness unlimited` - Max loudness boost
• `/pitch unlimited` - Max pitch adjustment
• `/reverb unlimited` - Max reverb effect
• `/settings [key=value]` - View/change audio settings (e.g., `/settings volume_boost=3.0`)
• `/tempo unlimited` - Max tempo adjustment
• `/volume unlimited` - Max volume boost

🛡️ **Security Commands (Admins only):**
• `/block` - Block user for 1 hour (reply to user)
• `/unblock` - Unblock user and reset warnings (reply to user)
• `/warn` or `/warnings` - Check user warnings (reply to user)

🔒 **Auto Security Features:**
• Anti-spam protection (max 5 messages/10s)
• Bad words filtering
• Phone number filtering
• OTP/sensitive code filtering
• Auto-warning system (3 warnings = 1-hour ban)

📊 **Status Commands:**
• `/status` - Show bot and stream status

❓ **Help:**
• `/help` or `/start` - Show this help message

**Note:** Commands auto-delete after 60 seconds for privacy. Use in allowed groups or private chats.
"""
    reply = await message.reply_text(help_text)
    asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["on", "startfx"]) & allowed_only)
async def cmd_on(client, message: Message):
    chat_id = message.chat.id
    try:
        await start_stream(chat_id)
        reply = await message.reply_text("🚀 𝘾𝙖𝙧𝙣𝙖𝙡 𝙇𝙞𝙫𝙚 𝙈𝙞𝙘 ON ho gaila 😎🎤")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("MIC_STARTED", f"Chat ID: {chat_id}\nStarted by: {message.from_user.mention}")
    except Exception as e:
        reply = await message.reply_text(f"❌ Start error: {e}")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("MIC_ERROR", f"Chat ID: {chat_id}\nError: {str(e)}")

@app.on_message(filters.command(["off", "stopfx"]) & allowed_only)
async def cmd_off(client, message: Message):
    chat_id = message.chat.id
    await stop_stream(chat_id)
    reply = await message.reply_text("🔴 𝘾𝙖𝙧𝙣𝙖𝙡 𝙈𝙞𝙘 OFF ho gaila ❌")
    asyncio.create_task(delete_message_with_delay(reply))
    await log_event("MIC_STOPPED", f"Chat ID: {chat_id}\nStopped by: {message.from_user.mention}")

@app.on_message(filters.command(["status"]) & allowed_only)
async def cmd_status(client, message: Message):
    mic_status = "RUNNING" if ff_mic.is_running() else "STOPPED"
    song_status = "RUNNING" if ff_song.is_running() else "STOPPED"
    call_status = "IN_CALL" if active_chats else "NOT_IN_CALL"
    active_chats_list = ", ".join(str(chat) for chat in active_chats) if active_chats else "None"
    
    reply = await message.reply_text(
        f"ℹ️ **Status**\n"
        f"FFmpeg Mic: {mic_status}\n"
        f"FFmpeg Song: {song_status}\n"
        f"Call: {call_status}\n"
        f"Active Chats: {active_chats_list}"
    )
    asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["settings"]) & allowed_only)
async def cmd_settings(client, message: Message):
    if len(message.command) > 1:
        try:
            args = message.command[1:]
            for arg in args:
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    if key in audio_settings.settings:
                        if isinstance(audio_settings.settings[key], int):
                            audio_settings.settings[key] = int(value)
                        elif isinstance(audio_settings.settings[key], float):
                            audio_settings.settings[key] = float(value)
                        else:
                            audio_settings.settings[key] = value
            
            audio_settings.save_settings()
            reply = await message.reply_text("✅ Settings updated and saved!")
            asyncio.create_task(delete_message_with_delay(reply))
            await log_event("SETTINGS_UPDATED", f"Updated by: {message.from_user.mention}\nSettings: {args}")
        except Exception as e:
            reply = await message.reply_text(f"❌ Error updating settings: {e}")
            asyncio.create_task(delete_message_with_delay(reply))
    else:
        settings_text = "**Current Audio Settings:**\n\n"
        for key, value in audio_settings.settings.items():
            settings_text += f"**{key}**: `{value}`\n"
        settings_text += "\n**To change:** `/settings key=value key2=value2`"
        reply = await message.reply_text(settings_text)
        asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["carnal"]) & allowed_only)
async def cmd_carnal(client, message: Message):
    chat_id = message.chat.id
    try:
        audio_settings.set_carnal_mode()
        await start_stream(chat_id)
        reply = await message.reply_text("🔥 𝙐𝙇𝙏𝙄𝙈𝘼𝙏𝙀 𝘾𝘼𝙍𝙉𝘼𝙇 𝙈𝙊𝘿𝙀 𝘼𝘾𝙏𝙄𝙑𝘼𝙏𝙀𝘿! 😈")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("CARNAL_MODE", f"Chat ID: {chat_id}\nActivated by: {message.from_user.mention}")
    except Exception as e:
        reply = await message.reply_text(f"❌ Carnal mode error: {e}")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("CARNAL_ERROR", f"Chat ID: {chat_id}\nError: {str(e)}")

@app.on_message(filters.command(["volume", "echo", "loudness", "bass", "reverb", "compressor", "pitch", "tempo"]) & allowed_only)
async def cmd_unlimited(client, message: Message):
    command = message.command[0].lower()
    
    if len(message.command) > 1 and message.command[1].lower() == "unlimited":
        audio_settings.set_unlimited_mode(command)
        reply = await message.reply_text(f"✅ 𝙐𝙉𝙇𝙄𝙈𝙄𝙏𝙀𝘿 {command.upper()} 𝘼𝘾𝙏𝙄𝙑𝘼𝙏𝙀𝘿! 🔊")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("UNLIMITED_MODE", f"Activated {command.upper()} by: {message.from_user.mention}")
    else:
        reply = await message.reply_text(f"**Usage:** `/{command} unlimited`")
        asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["play"]) & allowed_only)
async def cmd_play(client, message: Message):
    chat_id = message.chat.id
    
    try:
        song_path = await download_audio(message)
        await start_stream(chat_id, for_song=True, song_path=song_path)
        reply = await message.reply_text("🎵 𝙎𝙊𝙉𝙂 𝙋𝙇𝘼𝙔𝙄𝙉𝙂... 🎶")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("SONG_PLAYING", f"Chat ID: {chat_id}\nStarted by: {message.from_user.mention}")
        
        async def cleanup():
            await asyncio.sleep(10)
            try:
                os.remove(song_path)
            except:
                pass
        
        asyncio.create_task(cleanup())
        
    except Exception as e:
        reply = await message.reply_text(f"❌ Play error: {e}")
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("PLAY_ERROR", f"Chat ID: {chat_id}\nError: {str(e)}")

@app.on_message(filters.command(["activevc"]) & allowed_only)
async def cmd_activevc(client, message: Message):
    if not active_chats:
        reply = await message.reply_text("❌ 𝙆𝙊𝙄 𝘼𝘾𝙏𝙄𝙑𝙀 𝙑𝙊𝙄𝘾𝙀 𝘾𝙃𝘼𝙏 𝙉𝘼𝙃𝙄 𝙃𝘼𝙄")
        asyncio.create_task(delete_message_with_delay(reply))
        return
    
    active_list = "🔊 𝘼𝘾𝙏𝙄𝙑𝙀 𝙑𝙊𝙄𝘾𝙀 𝘾𝙃𝘼𝙏𝙎:\n\n"
    
    for chat_id in active_chats:
        try:
            chat = await app.get_chat(chat_id)
            chat_title = chat.title if chat.title else f"Private Chat ({chat_id})"
            active_list += f"• {chat_title} (ID: {chat_id})\n"
        except:
            active_list += f"• Unknown Chat (ID: {chat_id})\n"
    
    reply = await message.reply_text(active_list)
    asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["warn", "warnings"]) & allowed_only)
async def cmd_warnings(client, message: Message):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        warnings = security_system.get_warnings(user_id)
        user = message.reply_to_message.from_user
        
        reply = await message.reply_text(
            f"⚠️ **Warnings for {user.mention}**\n"
            f"Total warnings: {warnings}/{MAX_WARNINGS}"
        )
        asyncio.create_task(delete_message_with_delay(reply))
    else:
        reply = await message.reply_text("Please reply to a user's message to check their warnings")
        asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["block"]) & allowed_only)
async def cmd_block(client, message: Message):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user = message.reply_to_message.from_user
        
        security_system.block_user(user_id)
        reply = await message.reply_text(
            f"🚫 **User Blocked**\n"
            f"User: {user.mention}\n"
            f"Duration: 1 hour"
        )
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("USER_BLOCKED", f"Blocked by: {message.from_user.mention}\nUser: {user.mention}")
    else:
        reply = await message.reply_text("Please reply to a user's message to block them")
        asyncio.create_task(delete_message_with_delay(reply))

@app.on_message(filters.command(["unblock"]) & allowed_only)
async def cmd_unblock(client, message: Message):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user = message.reply_to_message.from_user
        
        security_system.reset_warnings(user_id)
        reply = await message.reply_text(
            f"✅ **User Unblocked**\n"
            f"User: {user.mention}\n"
            f"Warnings reset to 0"
        )
        asyncio.create_task(delete_message_with_delay(reply))
        await log_event("USER_UNBLOCKED", f"Unblocked by: {message.from_user.mention}\nUser: {user.mention}")
    else:
        reply = await message.reply_text("Please reply to a user's message to unblock them")
        asyncio.create_task(delete_message_with_delay(reply))

# ================== EVENT HANDLERS ==================

@app.on_message(filters.voice_chat_started)
async def voice_chat_started(client, message: Message):
    await log_event("VOICE_CHAT_STARTED", f"Chat: {message.chat.title}\nID: {message.chat.id}")

@app.on_message(filters.voice_chat_ended)
async def voice_chat_ended(client, message: Message):
    await log_event("VOICE_CHAT_ENDED", f"Chat: {message.chat.title}\nID: {message.chat.id}")
    await stop_stream(message.chat.id)

@app.on_message(filters.voice_chat_members_invited)
async def voice_chat_invited(client, message: Message):
    await log_event("VOICE_CHAT_INVITED", f"Chat: {message.chat.title}\nID: {message.chat.id}")

# ================== MAIN ==========================

async def main():
    if not command_exists("ffmpeg"):
        error_msg = "❌ Error: FFmpeg is not installed. Please install FFmpeg to run this bot."
        print(error_msg)
        await log_event("BOT_ERROR", error_msg)
        return
    
    if not check_node_version():
        error_msg = "❌ Error: Node.js (version 15.0.0 or higher) is not installed or not found in PATH. Please install Node.js."
        print(error_msg)
        await log_event("BOT_ERROR", error_msg)
        return
    
    try:
        await log_event("BOT_STARTING", "Carnal Live Mic Userbot is starting up...")
        await app.start()
        if not USE_GROUP_CALL_FACTORY:
            await call.start()
        
        startup_msg = """
✅ **Carnal Live Mic Userbot Started!**

🔥 **Features Activated:**
- Advanced Audio Processing
- Auto Security System
- Real-time Notifications
- Multi-chat Support

Use `/help` to see all available commands.
"""
        await send_notification(startup_msg)
        print("✅ Carnal Live Mic Userbot started!")
        print("🔥 Use /help to see all commands")
        
        # Keep the script alive
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        error_msg = f"❌ Unexpected error in main: {e}"
        print(error_msg)
        await log_event("BOT_ERROR", error_msg)
    finally:
        # Ensure proper cleanup
        await stop_all_streams()
        await app.stop()
        await log_event("BOT_STOPPED", "Carnal Live Mic Userbot has been stopped.")

async def stop_all_streams():
    """Stop all active streams and clean up"""
    for chat_id in list(active_chats):
        await stop_stream(chat_id)
    ff_mic.stop()
    ff_song.stop()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        loop.run_until_complete(stop_all_streams())
        loop.run_until_complete(app.stop())
        loop.run_until_complete(log_event("BOT_SHUTDOWN", "Bot was shut down by keyboard interrupt"))
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(error_msg)
        loop.run_until_complete(stop_all_streams())
        loop.run_until_complete(app.stop())
        loop.run_until_complete(log_event("BOT_CRASH", error_msg))
    finally:
        if not loop.is_closed():
            loop.close()