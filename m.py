import os
import asyncio
import sqlite3
import random
import string
import logging
import aiohttp
import time
from datetime import datetime, timedelta
from typing import List, Tuple

# Correct imports for aiogram 3.x+
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# Telethon imports
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.sessions import StringSession

# Configuration (assuming you have a config.py file)
try:
    import config
except ImportError:
    print("Error: config.py not found. Please create one with BOT_TOKEN, API_ID, API_HASH, and ADMINS.")
    exit()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# Database setup
conn = sqlite3.connect('smm_panel.db')
c = conn.cursor()

# Create tables
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, balance INTEGER, is_admin BOOLEAN, created_at TIMESTAMP)''')

c.execute('''CREATE TABLE IF NOT EXISTS accounts
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, session_string TEXT, 
              phone TEXT, is_active BOOLEAN, created_at TIMESTAMP, last_used TIMESTAMP,
              flood_wait_until TIMESTAMP, requests_count INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS services
             (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, duration_days INTEGER,
              price_per_100 INTEGER, min_order INTEGER, max_order INTEGER, 
              description TEXT, is_active BOOLEAN)''')

c.execute('''CREATE TABLE IF NOT EXISTS orders
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service_id INTEGER, 
              target_invite TEXT, quantity INTEGER, status TEXT, total_price INTEGER,
              created_at TIMESTAMP, completed_at TIMESTAMP, expires_at TIMESTAMP)''')

c.execute('''CREATE TABLE IF NOT EXISTS transactions
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, 
              type TEXT, description TEXT, created_at TIMESTAMP)''')

c.execute('''CREATE TABLE IF NOT EXISTS fake_members
             (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, first_name TEXT, 
              last_name TEXT, phone_number TEXT, session_string TEXT, is_used BOOLEAN,
              created_at TIMESTAMP, last_used TIMESTAMP, expires_at TIMESTAMP)''')

conn.commit()

# States for FSM
class UserStates(StatesGroup):
    waiting_for_target = State()
    waiting_for_quantity = State()
    adding_service = State()
    waiting_for_fake_member_count = State()

# Account rotation and flood wait bypass system
class AccountManager:
    def __init__(self):
        self.accounts = []
        self.update_accounts()
    
    def update_accounts(self):
        c.execute("SELECT id, session_string, flood_wait_until, requests_count FROM accounts WHERE is_active = TRUE")
        self.accounts = c.fetchall()
    
    def get_best_account(self):
        now = datetime.now()
        available_accounts = []
        
        for account in self.accounts:
            account_id, session_string, flood_wait_until, requests_count = account
            
            # Check if account is in flood wait
            if flood_wait_until and datetime.strptime(flood_wait_until, '%Y-%m-%d %H:%M:%S') > now:
                continue
            
            available_accounts.append((account_id, session_string, requests_count))
        
        if not available_accounts:
            return None
        
        # Return account with least requests
        available_accounts.sort(key=lambda x: x[2])
        return available_accounts[0]
    
    def mark_account_flood_wait(self, account_id, wait_time):
        wait_until = datetime.now() + timedelta(seconds=wait_time)
        c.execute("UPDATE accounts SET flood_wait_until = ? WHERE id = ?", 
                 (wait_until.strftime('%Y-%m-%d %H:%M:%S'), account_id))
        conn.commit()
        self.update_accounts()
    
    def increment_account_requests(self, account_id):
        c.execute("UPDATE accounts SET requests_count = requests_count + 1, last_used = ? WHERE id = ?",
                 (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), account_id))
        conn.commit()
        self.update_accounts()

# Initialize account manager
account_manager = AccountManager()

# Fake member generator - REAL FAKE ACCOUNTS BANAYEGA
class FakeMemberGenerator:
    @staticmethod
    def generate_phone_number():
        return f"+1{random.randint(200, 999)}{random.randint(100, 999)}{random.randint(1000, 9999)}"
    
    @staticmethod
    def generate_random_name():
        first_names = ["John", "Jane", "Robert", "Emily", "Michael", "Sarah", "David", "Lisa", "James", "Maria",
                      "William", "Laura", "Richard", "Amy", "Charles", "Michelle", "Joseph", "Rebecca", "Thomas", "Kim"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                     "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
        return f"{random.choice(first_names)}", f"{random.choice(last_names)}"
    
    @staticmethod
    def generate_random_username():
        prefixes = ["cool", "super", "mega", "ultra", "pro", "king", "queen", "star", "light", "dark"]
        suffixes = ["boy", "girl", "player", "gamer", "master", "legend", "warrior", "hero", "ninja", "rock"]
        numbers = random.randint(10, 999)
        return f"{random.choice(prefixes)}_{random.choice(suffixes)}{numbers}"
    
    @staticmethod
    async def create_fake_account():
        """Real fake account banata hai"""
        try:
            client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
            await client.start()
            
            first_name, last_name = FakeMemberGenerator.generate_random_name()
            username = FakeMemberGenerator.generate_random_username()
            
            await client(functions.account.UpdateProfileRequest(
                first_name=first_name,
                last_name=last_name,
                about="Hello! I'm new here."
            ))
            
            try:
                await client(functions.account.UpdateUsernameRequest(username=username))
            except Exception:
                pass
            
            session_string = client.session.save()
            
            await client.disconnect()
            
            c.execute("INSERT INTO fake_members (username, first_name, last_name, phone_number, session_string, is_used, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (username, first_name, last_name, "", session_string, False, datetime.now()))
            conn.commit()
            
            return True
        except Exception as e:
            logger.error(f"Error creating fake account: {e}")
            return False

# Admin keyboard
def admin_keyboard():
    keyboard_buttons = [
        [
            InlineKeyboardButton(text="➕ Add Service", callback_data="add_service"),
            InlineKeyboardButton(text="📊 Statistics", callback_data="stats")
        ],
        [
            InlineKeyboardButton(text="👥 Users", callback_data="users_list"),
            InlineKeyboardButton(text="💼 Accounts", callback_data="accounts_list")
        ],
        [
            InlineKeyboardButton(text="🤖 Create Fake Members", callback_data="create_fake_members")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

# User keyboard
def user_keyboard():
    keyboard_buttons = [
        [
            InlineKeyboardButton(text="📊 My Balance", callback_data="my_balance"),
            InlineKeyboardButton(text="🛒 Add Members", callback_data="add_members")
        ],
        [
            InlineKeyboardButton(text="💳 Add Funds", callback_data="add_funds"),
            InlineKeyboardButton(text="📦 My Orders", callback_data="my_orders")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

# Services keyboard
def services_keyboard():
    c.execute("SELECT id, name, duration_days, price_per_100, description FROM services WHERE is_active = TRUE")
    services = c.fetchall()
    
    keyboard_buttons = []
    for service in services:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{service[1]} - {service[2]} days - ₹{service[3]}/100 members", 
                callback_data=f"service_{service[0]}"
            )
        ])
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

# Start command
@router.message(CommandStart())
async def send_welcome(message: Message):
    user_id = message.from_user.id
    
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    
    if not user:
        c.execute("INSERT INTO users (user_id, balance, is_admin, created_at) VALUES (?, ?, ?, ?)",
                 (user_id, 0, False, datetime.now()))
        conn.commit()
    
    if user_id in config.ADMINS:
        await message.reply("👋 Welcome Admin!", reply_markup=admin_keyboard())
    else:
        await message.reply("👋 Welcome to Member Transfer Bot!", reply_markup=user_keyboard())

# Add members command
@router.callback_query(F.data == 'add_members')
async def process_add_members(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    c.execute("SELECT COUNT(*) FROM services WHERE is_active = TRUE")
    service_count = c.fetchone()[0]
    
    if service_count == 0:
        await bot.send_message(callback_query.from_user.id, "❌ No services available. Please contact admin.")
        return
    
    await bot.send_message(
        callback_query.from_user.id,
        "Select a service plan:",
        reply_markup=services_keyboard()
    )

# Service selection handler
@router.callback_query(F.data.startswith('service_'))
async def process_service_selection(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    service_id = int(callback_query.data.split('_')[1])
    
    c.execute("SELECT name, duration_days, price_per_100, min_order, max_order FROM services WHERE id = ?", (service_id,))
    service = c.fetchone()
    
    if not service:
        await bot.send_message(callback_query.from_user.id, "❌ Service not found.")
        return
    
    service_name, duration_days, price_per_100, min_order, max_order = service
    
    await state.update_data(
        service_id=service_id,
        duration_days=duration_days,
        price_per_100=price_per_100
    )
    
    await bot.send_message(
        callback_query.from_user.id,
        f"✅ Selected: {service_name} ({duration_days} days)\n"
        f"Price: ₹{price_per_100} per 100 members\n\n"
        f"Now send the target group invite link:"
    )
    await state.set_state(UserStates.waiting_for_target)

# Target group handler
@router.message(UserStates.waiting_for_target)
async def process_target_group(message: Message, state: FSMContext):
    await state.update_data(target_invite=message.text)
    
    await message.reply("How many members do you want to add?")
    await state.set_state(UserStates.waiting_for_quantity)

# Quantity handler
@router.message(UserStates.waiting_for_quantity)
async def process_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text)
        user_id = message.from_user.id
        
        data = await state.get_data()
        service_id = data.get('service_id')
        duration_days = data.get('duration_days')
        price_per_100 = data.get('price_per_100')
        target_invite = data.get('target_invite')
        
        if not service_id:
            await message.reply("❌ Session expired. Please start over with /start.")
            await state.clear()
            return
            
        c.execute("SELECT min_order, max_order FROM services WHERE id = ?", (service_id,))
        min_max = c.fetchone()
        min_order, max_order = min_max if min_max else (1, 1000)
        
        if not (min_order <= quantity <= max_order):
            await message.reply(f"❌ Order quantity must be between {min_order} and {max_order}.")
            await state.clear()
            return
        
        price = (quantity * price_per_100) // 100
        
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_data = c.fetchone()
        balance = user_data[0] if user_data else 0
        
        if balance < price:
            await message.reply(f"❌ Insufficient balance. You need ₹{price}. Current balance: ₹{balance}")
            await state.clear()
            return
        
        c.execute("SELECT COUNT(*) FROM fake_members WHERE is_used = FALSE")
        available_members = c.fetchone()[0]
        
        if quantity > available_members:
            await message.reply(f"❌ Only {available_members} fake members available. Please create more or order less.")
            await state.clear()
            return
        
        expires_at = datetime.now() + timedelta(days=duration_days)
        c.execute("INSERT INTO orders (user_id, service_id, target_invite, quantity, status, total_price, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (user_id, service_id, target_invite, quantity, 'pending', price, datetime.now(), expires_at))
        order_id = c.lastrowid
        conn.commit()
        
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
        conn.commit()
        
        c.execute("INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?, ?, ?, ?, ?)",
                 (user_id, -price, 'debit', f'Order #{order_id} - {quantity} members for {duration_days} days', datetime.now()))
        conn.commit()
        
        await message.reply(
            f"✅ Order placed!\n"
            f"Order ID: #{order_id}\n"
            f"Members: {quantity}\n"
            f"Duration: {duration_days} days\n"
            f"Price: ₹{price}\n"
            f"Processing will start shortly."
        )
        
        asyncio.create_task(process_fake_members_order(order_id, target_invite, quantity, user_id, duration_days))
        
    except ValueError:
        await message.reply("❌ Please enter a valid number.")
    
    await state.clear()

# Add fake member to group with duration
async def add_fake_member_to_group(session_string, target_invite, duration_days):
    client = TelegramClient(StringSession(session_string), config.API_ID, config.API_HASH)
    
    try:
        await client.start()
        
        if 't.me' in target_invite and ('joinchat' in target_invite or '+' in target_invite):
            hash = target_invite.split('joinchat/')[-1] if 'joinchat/' in target_invite else target_invite.split('/')[-1]
            await client(ImportChatInviteRequest(hash))
        else:
            await client(JoinChannelRequest(target_invite))
        
        if duration_days == 0:
            stay_minutes = random.uniform(1440, 2880)
        else:
            stay_minutes = random.uniform(60 * duration_days * 0.8, 60 * duration_days * 1.2)
        
        bios = [
            "Hello! Nice to meet you all!",
            "New here, looking forward to chatting!",
            "Just joined this amazing group!",
            "Hi everyone! Excited to be here!",
            "Hello friends! Great to join this community!"
        ]
        try:
            await client(functions.account.UpdateProfileRequest(about=random.choice(bios)))
        except Exception:
            pass
        
        await asyncio.sleep(stay_minutes * 60)
        
        return True
        
    except errors.FloodWaitError as e:
        logger.warning(f"FloodWait: Need to wait {e.seconds} seconds")
        return False
    except (errors.InviteHashInvalidError, errors.InviteHashExpiredError):
        logger.warning("Invalid or expired invite hash.")
        return False
    except Exception as e:
        logger.error(f"Error adding fake member: {str(e)}")
        return False
    finally:
        try:
            if client and client.is_connected():
                await client.disconnect()
        except Exception:
            pass

# Process fake members order with duration
async def process_fake_members_order(order_id, target_invite, quantity, user_id, duration_days):
    try:
        c.execute("UPDATE orders SET status = ? WHERE id = ?", ('processing', order_id))
        conn.commit()
        
        members_added = 0
        progress_message = await bot.send_message(user_id, f"🔄 Processing order #{order_id}\nProgress: 0/{quantity} (0%)")
        
        c.execute("SELECT id, session_string FROM fake_members WHERE is_used = FALSE LIMIT ?", (quantity,))
        fake_members = c.fetchall()
        
        if not fake_members:
            await bot.send_message(user_id, "❌ No fake members available.")
            c.execute("UPDATE orders SET status = ? WHERE id = ?", ('failed', order_id))
            conn.commit()
            return
        
        for member_id, session_string in fake_members:
            if members_added >= quantity:
                break
                
            success = await add_fake_member_to_group(session_string, target_invite, duration_days)
            
            if success:
                members_added += 1
                expires_at = datetime.now() + timedelta(days=duration_days)
                c.execute("UPDATE fake_members SET is_used = TRUE, last_used = ?, expires_at = ? WHERE id = ?",
                         (datetime.now(), expires_at, member_id))
                conn.commit()
                
                progress = (members_added / quantity) * 100
                await progress_message.edit_text(
                    f"🔄 Processing order #{order_id}\nProgress: {members_added}/{quantity} ({progress:.1f}%)"
                )
            
            await asyncio.sleep(random.uniform(10, 30))
        
        if members_added >= quantity * 0.8:
            status = 'completed'
            message = f"✅ Order #{order_id} completed!\nMembers added: {members_added}/{quantity}\nDuration: {duration_days} days"
        else:
            status = 'partial'
            message = f"⚠️ Order #{order_id} partially completed!\nMembers added: {members_added}/{quantity}\nDuration: {duration_days} days"
        
        c.execute("UPDATE orders SET status = ?, completed_at = ? WHERE id = ?", 
                 (status, datetime.now(), order_id))
        conn.commit()
        
        await progress_message.edit_text(message)
        
    except Exception as e:
        logger.error(f"Error processing order: {e}")
        c.execute("UPDATE orders SET status = ? WHERE id = ?", ('failed', order_id))
        conn.commit()
        await bot.send_message(user_id, f"❌ Order #{order_id} failed: {str(e)}")

# Add service callback (admin only)
@router.callback_query(F.data == 'add_service')
async def process_add_service(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id not in config.ADMINS:
        await callback_query.answer("You are not an admin.")
        return
        
    await callback_query.answer()
    await bot.send_message(
        callback_query.from_user.id,
        "Please send service details in format:\n"
        "**Name**|**Duration Days**|**Price per 100**|**Min Order**|**Max Order**|**Description**\n\n"
        "Example: `Premium 30 Days|30|200|10|1000|High quality members for 30 days`"
    )
    await state.set_state(UserStates.adding_service)

# Add service handler
@router.message(UserStates.adding_service)
async def process_service_details(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMINS:
        await message.reply("You are not an admin.")
        await state.clear()
        return
        
    try:
        parts = message.text.split('|')
        if len(parts) < 6:
            await message.reply("❌ Invalid format. Please use: Name|Duration Days|Price per 100|Min Order|Max Order|Description")
            return
        
        name = parts[0]
        duration_days = int(parts[1])
        price_per_100 = int(parts[2])
        min_order = int(parts[3])
        max_order = int(parts[4])
        description = '|'.join(parts[5:])
        
        c.execute("INSERT INTO services (name, duration_days, price_per_100, min_order, max_order, description, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (name, duration_days, price_per_100, min_order, max_order, description, True))
        conn.commit()
        
        await message.reply("✅ Service added successfully!")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
    
    await state.clear()

# Create fake members (admin only)
@router.callback_query(F.data == 'create_fake_members')
async def process_create_fake_members(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id not in config.ADMINS:
        await callback_query.answer("You are not an admin.")
        return
        
    await callback_query.answer()
    
    await bot.send_message(
        callback_query.from_user.id,
        "How many fake members do you want to create?\n\n"
        "Note: This may take some time. Recommended: 10-20 at a time."
    )
    
    await state.set_state(UserStates.waiting_for_fake_member_count)

# Handler for fake member count
@router.message(UserStates.waiting_for_fake_member_count)
async def process_fake_member_count(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMINS:
        await message.reply("You are not an admin.")
        await state.clear()
        return
        
    try:
        count = int(message.text)
        if count > 50:
            await message.reply("❌ Maximum 50 fake members at a time for safety.")
            await state.clear()
            return
        
        await message.reply(f"🔄 Creating {count} fake members. This may take a while...")
        
        success_count = 0
        for i in range(count):
            success = await FakeMemberGenerator.create_fake_account()
            if success:
                success_count += 1
            
            if (i + 1) % 5 == 0:
                await message.reply(f"Created {i + 1}/{count} fake members...")
            
            await asyncio.sleep(10)
        
        await message.reply(f"✅ Successfully created {success_count}/{count} fake members!")
        
    except ValueError:
        await message.reply("❌ Please enter a valid number.")
    
    await state.clear()

# My orders callback
@router.callback_query(F.data == 'my_orders')
async def process_my_orders(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    c.execute('''SELECT o.id, s.name, o.quantity, o.total_price, o.status, o.created_at, o.expires_at 
                 FROM orders o 
                 JOIN services s ON o.service_id = s.id 
                 WHERE o.user_id = ? 
                 ORDER BY o.created_at DESC LIMIT 10''', (user_id,))
    orders = c.fetchall()
    
    if not orders:
        await bot.send_message(user_id, "📦 You don't have any orders yet.")
        return
    
    message = "📦 Your recent orders:\n\n"
    for order in orders:
        order_id, service_name, quantity, price, status, created_at, expires_at = order
        message += (f"**Order ID:** #{order_id}\n**Service:** {service_name}\n**Quantity:** {quantity}\n"
                   f"**Price:** ₹{price}\n**Status:** {status}\n**Date:** {created_at}\n")
        
        if expires_at:
            message += f"**Expires:** {expires_at}\n"
        
        message += "---"
        
    await bot.send_message(user_id, message, parse_mode='Markdown')

# Back to main menu
@router.callback_query(F.data == 'back_to_main')
async def back_to_main_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    
    if user_id in config.ADMINS:
        await bot.send_message(user_id, "Returning to Admin menu.", reply_markup=admin_keyboard())
    else:
        await bot.send_message(user_id, "Returning to Main menu.", reply_markup=user_keyboard())

# Register router and run bot
async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())