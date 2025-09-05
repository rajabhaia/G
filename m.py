import os
import asyncio
import sqlite3
import random
import string
from datetime import datetime, timedelta
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest, InviteToChannelRequest
from telethon.tl.types import InputPeerUser, InputPeerChannel, InputChatInvite
from telethon.sessions import StringSession
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import aiohttp
import time
from typing import List, Tuple
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

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

# States
class UserStates(StatesGroup):
    waiting_for_target = State()
    waiting_for_quantity = State()
    waiting_for_service = State()
    waiting_for_payment = State()
    adding_account = State()
    adding_service = State()

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
            # Naya session banaye
            client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
            await client.start()
            
            # Account details set kare
            first_name, last_name = FakeMemberGenerator.generate_random_name()
            username = FakeMemberGenerator.generate_random_username()
            
            # Profile update kare
            await client(functions.account.UpdateProfileRequest(
                first_name=first_name,
                last_name=last_name,
                about="Hello! I'm new here."
            ))
            
            # Username set kare (agar available hai)
            try:
                await client(functions.account.UpdateUsernameRequest(username=username))
            except:
                pass  # Username already taken
            
            # Session string save kare
            session_string = client.session.save()
            
            await client.disconnect()
            
            # Database mein save kare
            c.execute("INSERT INTO fake_members (username, first_name, last_name, phone_number, session_string, is_used, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (username, first_name, last_name, "", session_string, False, datetime.now()))
            conn.commit()
            
            return True
        except Exception as e:
            logger.error(f"Error creating fake account: {e}")
            return False

# Admin keyboard
def admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Add Service", callback_data="add_service"),
        InlineKeyboardButton("📊 Statistics", callback_data="stats"),
        InlineKeyboardButton("👥 Users", callback_data="users_list"),
        InlineKeyboardButton("💼 Accounts", callback_data="accounts_list"),
        InlineKeyboardButton("🤖 Create Fake Members", callback_data="create_fake_members")
    )
    return keyboard

# User keyboard
def user_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 My Balance", callback_data="my_balance"),
        InlineKeyboardButton("🛒 Add Members", callback_data="add_members"),
        InlineKeyboardButton("💳 Add Funds", callback_data="add_funds"),
        InlineKeyboardButton("📦 My Orders", callback_data="my_orders")
    )
    return keyboard

# Services keyboard
def services_keyboard():
    c.execute("SELECT id, name, duration_days, price_per_100, description FROM services WHERE is_active = TRUE")
    services = c.fetchall()
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for service in services:
        keyboard.add(InlineKeyboardButton(
            f"{service[1]} - {service[2]} days - ₹{service[3]}/100 members", 
            callback_data=f"service_{service[0]}"
        ))
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="back_to_main"))
    return keyboard

# Start command
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    
    # Check if user exists
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    
    if not user:
        # Add new user
        c.execute("INSERT INTO users (user_id, balance, is_admin, created_at) VALUES (?, ?, ?, ?)",
                 (user_id, 0, False, datetime.now()))
        conn.commit()
    
    if user_id in config.ADMINS:
        await message.reply("👋 Welcome Admin!", reply_markup=admin_keyboard())
    else:
        await message.reply("👋 Welcome to Member Transfer Bot!", reply_markup=user_keyboard())

# Add members command
@dp.callback_query_handler(lambda c: c.data == 'add_members')
async def process_add_members(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    # Show available services
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
@dp.callback_query_handler(lambda c: c.data.startswith('service_'))
async def process_service_selection(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    
    service_id = int(callback_query.data.split('_')[1])
    
    # Get service details
    c.execute("SELECT name, duration_days, price_per_100, min_order, max_order FROM services WHERE id = ?", (service_id,))
    service = c.fetchone()
    
    if not service:
        await bot.send_message(callback_query.from_user.id, "❌ Service not found.")
        return
    
    service_name, duration_days, price_per_100, min_order, max_order = service
    
    # Store service ID in state
    async with state.proxy() as data:
        data['service_id'] = service_id
        data['duration_days'] = duration_days
        data['price_per_100'] = price_per_100
    
    await bot.send_message(
        callback_query.from_user.id,
        f"✅ Selected: {service_name} ({duration_days} days)\n"
        f"Price: ₹{price_per_100} per 100 members\n\n"
        f"Now send the target group invite link:"
    )
    await UserStates.waiting_for_target.set()

# Target group handler
@dp.message_handler(state=UserStates.waiting_for_target)
async def process_target_group(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['target_invite'] = message.text
    
    await message.reply("How many members do you want to add?")
    await UserStates.waiting_for_quantity.set()

# Quantity handler
@dp.message_handler(state=UserStates.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        user_id = message.from_user.id
        
        async with state.proxy() as data:
            service_id = data['service_id']
            duration_days = data['duration_days']
            price_per_100 = data['price_per_100']
            target_invite = data['target_invite']
        
        # Check min and max order
        c.execute("SELECT min_order, max_order FROM services WHERE id = ?", (service_id,))
        min_max = c.fetchone()
        min_order, max_order = min_max if min_max else (1, 1000)
        
        if quantity < min_order:
            await message.reply(f"❌ Minimum order is {min_order} members.")
            await state.finish()
            return
        
        if quantity > max_order:
            await message.reply(f"❌ Maximum order is {max_order} members.")
            await state.finish()
            return
        
        # Calculate price
        price = (quantity * price_per_100) // 100
        
        # Check user balance
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_data = c.fetchone()
        balance = user_data[0] if user_data else 0
        
        if balance < price:
            await message.reply(f"❌ Insufficient balance. You need ₹{price}. Current balance: ₹{balance}")
            await state.finish()
            return
        
        # Check available fake members
        c.execute("SELECT COUNT(*) FROM fake_members WHERE is_used = FALSE")
        available_members = c.fetchone()[0]
        
        if quantity > available_members:
            await message.reply(f"❌ Only {available_members} fake members available. Please create more or order less.")
            await state.finish()
            return
        
        # Create order
        expires_at = datetime.now() + timedelta(days=duration_days)
        c.execute("INSERT INTO orders (user_id, service_id, target_invite, quantity, status, total_price, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (user_id, service_id, target_invite, quantity, 'pending', price, datetime.now(), expires_at))
        order_id = c.lastrowid
        conn.commit()
        
        # Deduct balance
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
        conn.commit()
        
        # Add transaction
        c.execute("INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?, ?, ?, ?, ?)",
                 (user_id, -price, 'debit', f'Order #{order_id} - {quantity} members for {duration_days} days', datetime.now()))
        conn.commit()
        
        # Start processing
        await message.reply(
            f"✅ Order placed!\n"
            f"Order ID: #{order_id}\n"
            f"Members: {quantity}\n"
            f"Duration: {duration_days} days\n"
            f"Price: ₹{price}\n"
            f"Processing will start shortly."
        )
        
        # Process the order in background
        asyncio.create_task(process_fake_members_order(order_id, target_invite, quantity, user_id, duration_days))
        
    except ValueError:
        await message.reply("❌ Please enter a valid number.")
    
    await state.finish()

# Process fake members order with duration
async def process_fake_members_order(order_id, target_invite, quantity, user_id, duration_days):
    try:
        # Update order status
        c.execute("UPDATE orders SET status = ? WHERE id = ?", ('processing', order_id))
        conn.commit()
        
        members_added = 0
        progress_message = await bot.send_message(user_id, f"🔄 Processing order #{order_id}\nProgress: 0/{quantity} (0%)")
        
        # Get available fake members
        c.execute("SELECT id, session_string FROM fake_members WHERE is_used = FALSE LIMIT ?", (quantity,))
        fake_members = c.fetchall()
        
        if not fake_members:
            await bot.send_message(user_id, "❌ No fake members available.")
            c.execute("UPDATE orders SET status = ? WHERE id = ?", ('failed', order_id))
            conn.commit()
            return
        
        # Process each fake member
        for member_id, session_string in fake_members:
            if members_added >= quantity:
                break
                
            success = await add_fake_member_to_group(session_string, target_invite, duration_days)
            
            if success:
                members_added += 1
                
                # Mark member as used and set expiry
                expires_at = datetime.now() + timedelta(days=duration_days)
                c.execute("UPDATE fake_members SET is_used = TRUE, last_used = ?, expires_at = ? WHERE id = ?",
                         (datetime.now(), expires_at, member_id))
                conn.commit()
                
                # Update progress
                progress = (members_added / quantity) * 100
                await progress_message.edit_text(
                    f"🔄 Processing order #{order_id}\nProgress: {members_added}/{quantity} ({progress:.1f}%)"
                )
            
            # Random delay to avoid detection (10-30 seconds)
            await asyncio.sleep(random.uniform(10, 30))
        
        # Update order status
        if members_added >= quantity * 0.8:  # At least 80% success
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

# Add fake member to group with duration
async def add_fake_member_to_group(session_string, target_invite, duration_days):
    client = TelegramClient(StringSession(session_string), config.API_ID, config.API_HASH)
    
    try:
        await client.start()
        
        # Join target group using invite link
        if 't.me' in target_invite and 'joinchat' in target_invite:
            # Private group invite
            hash = target_invite.split('/')[-1]
            await client(ImportChatInviteRequest(hash))
        else:
            # Public group/channel
            await client(JoinChannelRequest(target_invite))
        
        # Stay in group based on duration
        if duration_days == 0:  # Permanent
            stay_minutes = random.uniform(1440, 2880)  # 1-2 days
        else:
            # Calculate stay time based on duration (longer for longer durations)
            stay_minutes = random.uniform(60 * duration_days * 0.8, 60 * duration_days * 1.2)
        
        # Change profile to look more real
        try:
            # Random bio set kare
            bios = [
                "Hello! Nice to meet you all!",
                "New here, looking forward to chatting!",
                "Just joined this amazing group!",
                "Hi everyone! Excited to be here!",
                "Hello friends! Great to join this community!"
            ]
            await client(functions.account.UpdateProfileRequest(about=random.choice(bios)))
        except:
            pass
        
        # Simulate some activity
        await asyncio.sleep(stay_minutes * 60)  # Convert minutes to seconds
        
        return True
        
    except errors.FloodWaitError as e:
        logger.warning(f"FloodWait: Need to wait {e.seconds} seconds")
        return False
        
    except errors.InviteHashInvalidError:
        logger.warning("Invalid invite hash")
        return False
        
    except errors.InviteHashExpiredError:
        logger.warning("Expired invite hash")
        return False
        
    except Exception as e:
        logger.error(f"Error adding fake member: {str(e)}")
        return False
        
    finally:
        try:
            await client.disconnect()
        except:
            pass

# Add service callback (admin only)
@dp.callback_query_handler(lambda c: c.data == 'add_service', user_id=config.ADMINS)
async def process_add_service(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        "Please send service details in format:\n"
        "Name|Duration Days|Price per 100|Min Order|Max Order|Description\n\n"
        "Example: Premium 30 Days|30|200|10|1000|High quality members for 30 days"
    )
    await UserStates.adding_service.set()

# Add service handler
@dp.message_handler(state=UserStates.adding_service, user_id=config.ADMINS)
async def process_service_details(message: types.Message, state: FSMContext):
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
        
        # Save service
        c.execute("INSERT INTO services (name, duration_days, price_per_100, min_order, max_order, description, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (name, duration_days, price_per_100, min_order, max_order, description, True))
        conn.commit()
        
        await message.reply("✅ Service added successfully!")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
    
    await state.finish()

# Create fake members (admin only)
@dp.callback_query_handler(lambda c: c.data == 'create_fake_members', user_id=config.ADMINS)
async def process_create_fake_members(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    await bot.send_message(
        callback_query.from_user.id,
        "How many fake members do you want to create?\n\n"
        "Note: This may take some time. Recommended: 10-20 at a time."
    )
    
    # Set state for creating fake members
    async with FSMContext(storage, callback_query.from_user.id, callback_query.from_user.id) as state:
        await state.set_state('waiting_for_fake_member_count')

# Handler for fake member count
@dp.message_handler(state='waiting_for_fake_member_count', user_id=config.ADMINS)
async def process_fake_member_count(message: types.Message):
    try:
        count = int(message.text)
        if count > 50:
            await message.reply("❌ Maximum 50 fake members at a time for safety.")
            return
        
        await message.reply(f"🔄 Creating {count} fake members. This may take a while...")
        
        success_count = 0
        for i in range(count):
            success = await FakeMemberGenerator.create_fake_account()
            if success:
                success_count += 1
            
            # Progress update
            if (i + 1) % 5 == 0:
                await message.reply(f"Created {i + 1}/{count} fake members...")
            
            # Delay between creations
            await asyncio.sleep(10)
        
        await message.reply(f"✅ Successfully created {success_count}/{count} fake members!")
        
    except ValueError:
        await message.reply("❌ Please enter a valid number.")

# My orders callback
@dp.callback_query_handler(lambda c: c.data == 'my_orders')
async def process_my_orders(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
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
        message += (f"Order #{order_id}\nService: {service_name}\nQuantity: {quantity}\n"
                   f"Price: ₹{price}\nStatus: {status}\nDate: {created_at}\n")
        
        if expires_at:
            message += f"Expires: {expires_at}\n"
        
        message += "\n"
    
    await bot.send_message(user_id, message)

# Run bot
if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)