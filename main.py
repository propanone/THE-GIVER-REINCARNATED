import discord
import os
import random
import json
import asyncio
from datetime import datetime, time, timedelta, timezone
from dotenv import load_dotenv
from discord.ext import commands, tasks
from keep_alive import keep_alive
import sys
import traceback
import shutil

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 950063903394631710
LEADERBOARD_IMAGE_URL = "https://media.discordapp.net/attachments/588488751974449163/1388201522348691466/sddefault.png?ex=68601eea&is=685ecd6a&hm=559323f7e27a0f53c67751d524d554c79e4a09f99ce3408f50cf50085ae993a4&=&format=webp&quality=lossless"
LEADERBOARD_CHANNEL_ID = 1369760540695592980
LOYALTY_WEIGHT = 0.2
ADMIN_USER_IDS = [569924649417441291]

ROLE_CONFIG = { "MRBAB": {"id": 1388197495133306941, "weight": 1, "points": 15}, "Rajel": {"id": 1369759295947935806, "weight": 250, "points": 2}, "NPC": {"id": 1369759970043760640, "weight": 250, "points": 1}, "Gay": {"id": 1369760023135391866, "weight": 250, "points": -1}, "Na9ch": {"id": 1369759897771577354, "weight": 249, "points": -2} }
TOKEN_REWARDS = { "MRBAB": 25, "Rajel": 10, "NPC": 5, "Gay": 2, "Na9ch": 0 }
SHOP_ITEMS = { "safety_net": {"price": 70, "name": "Safety Net", "description": "A one-time use item. Your next roll is guaranteed not to be 'Na9ch'. If you roll it, you'll get 'NPC' instead."}, 
               "lucky_clover": {"price": 50, "name": "Lucky Clover", "description": "A one-time use item. If your next roll is a negative-point role, you have a 25% chance to re-roll instantly."},
               "cooldown_cooler": {"price": 100, "name": "Cooldown Cooler", "description": "Instantly resets your 20-hour gambling cooldown. Can only be purchased once every 7 days."} }
WORKSHOP_ITEMS = {
    "second_roll": {"price": 5000, "name": "The Second Roll", "description": "Permanently halves your gambling cooldown."},
    "luck_tweak": {"price": 1000, "name": "Master Craftsman's Tweak", "description": "A permanent upgrade. Slightly increases the weight of all positive roles for you by 2%."},
    "mystats_color": {"price": 100, "name": "Cosmetic Flair", "description": "Purchase a unique hex color for your `!mystats` embed to show off your status. Usage: `!upgrade mystats_color #RRGGBB`"},
    "loyalty_boost": {"price": 2500, "name": "Loyalty Card", "description": "A permanent upgrade. Increases the loyalty weight you receive for each play by an extra 0.1."}
}
STREAK_REWARDS = { 3: {"tokens": 15, "message": "You're on a 3-day streak!"}, 7: {"tokens": 50, "message": "A 7-day streak!"}, 14: {"tokens": 125, "message": "A two-week streak!"}, 30: {"tokens": 300, "message": "A 30-DAY STREAK! true gambler."} }
PLAY_MILESTONES = { 10: {"tokens": 25, "message": "You've made your 10th roll! Welcome to the club."}, 25: {"tokens": 75, "message": "Congrats on 25 total plays!"}, 50: {"tokens": 150, "message": "Halfway to 100!"}, 100: {"tokens": 400, "message": "You are now a Gambling Centurion with 100 plays!"} }
EVENT_CONFIG = { "jackpot_fever": {"name": "Jackpot Fever", "description": "The MRBAB 'pity system' builds up twice as fast!", "modifier_type": "mrbab_pity_multiplier", "value": 2.0},
                 "lucky_hour": {"name": "Lucky Hour", "description": "All positive-point roles are 25% more likely to be rolled!", "modifier_type": "weight_boost_positive", "value": 1.25}, 
                 "unlucky_hour": {"name": "Unlucky Hour", "description": "All negative-point roles are 50% more likely to be rolled! Watch out!", "modifier_type": "weight_boost_negative", "value": 1.50},
                 "chaos": {"name": "Chaos Mode", "description": "All role weights are completely randomized! Anything could happen!", "modifier_type": "randomize_all", "value": None},
                 "lgbt_day": {"name": "LGBT + Na9ch Day", "description": "A day of opposites! All role points are inverted. Bad is good and good is bad! (MRBAB remains the jackpot).", "modifier_type": "invert_points", "value": None}, 
                 "coolday": {"name": "Coolday", "description": "It's a Coolday! The gambling cooldown is reduced to only 4 hours for the duration of this event!", "modifier_type": "cooldown_reduction", "value": 4}, 
                 "double_points": {"name": "Double Points", "description": "All points (positive and negative) from roles are doubled!", "modifier_type": "point_multiplier", "value": 2.0},
                 "token_rush": {"name": "Token Rush", "description": "TOKEN RUSH! All token rewards from gambling are TRIPLED!", "modifier_type": "token_multiplier", "value": 3.0} }

MRBAB_WEIGHT_INCREASE = 0.01
COOLDOWN_HOURS = 20
RANDOM_EVENT_CHANCE = 0.25

# --- FILE PATHS ---
COOLDOWN_FILE, PLAYER_STATS_FILE, ROLE_EXPIRATIONS_FILE, WEEKLY_STATS_FILE, GAME_STATE_FILE, PLAYER_WALLETS_FILE, PLAYER_INVENTORIES_FILE, PLAYER_UPGRADES_FILE = "cooldowns.json", "player_stats.json", "role_expirations.json", "weekly_stats.json", "game_state.json", "player_wallets.json", "player_inventories.json", "player_upgrades.json"

# --- DATA HANDLING & HELPER FUNCTIONS ---
def load_data(file_path):
    default = [] if 'expirations' in file_path else {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: return default
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError): return default
def save_data(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

def resolve_filepath(base_path):
    try:
        with open(GAME_STATE_FILE, 'r', encoding='utf-8') as f:
            game_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        game_state = {}
    if game_state.get("dev_mode", False):
        directory, filename = os.path.split(base_path)
        name, ext = os.path.splitext(filename)
        dev_filename = f"{name}_dev{ext}"
        return os.path.join(directory, dev_filename)
    return base_path

def get_active_event():
    game_state = load_data(resolve_filepath(GAME_STATE_FILE))
    event_name, end_time_str = game_state.get("active_event"), game_state.get("event_end_time")
    if not event_name or not end_time_str: return None, None
    end_time = datetime.fromisoformat(end_time_str)
    if datetime.now() > end_time:
        if "active_event" in game_state: del game_state["active_event"]
        if "event_end_time" in game_state: del game_state["event_end_time"]
        save_data(game_state, resolve_filepath(GAME_STATE_FILE))
        return None, None
    return event_name, end_time
def is_allowed_user():
    def predicate(ctx: commands.Context) -> bool: return ctx.author.id in ADMIN_USER_IDS
    return commands.check(predicate)

# --- BOT SETUP ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, case_insensitive=True)
        self.remove_command('help')
        
    async def setup_hook(self):
        self.add_view(RandomRoleView())
        print("Persistent view added.")
    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')
        daily_board_post.start()
        check_role_expirations.start()
        weekly_highlights_post.start()
        random_event_starter.start()
        print("Bot is ready and listening for commands.")
bot = MyBot()

@bot.check
async def dev_mode_check(ctx: commands.Context):
    game_state = load_data(GAME_STATE_FILE)
    if game_state.get("dev_mode", False):
        return ctx.author.id in ADMIN_USER_IDS
    return True

# --- UI VIEWS ---
class CoinFlipView(discord.ui.View):
    def __init__(self, author: discord.Member, bet_amount: int):
        super().__init__(timeout=30.0)
        self.author = author
        self.bet_amount = bet_amount
        self.choice = None
        self.result_message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your coin flip!", ephemeral=True)
            return False
        return True

    async def handle_flip(self, interaction: discord.Interaction, choice: str):
        for item in self.children:
            item.disabled = True
        self.stop()
        result = random.choice(["heads", "tails"])
        user_id_str = str(self.author.id)
        wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
        user_wallet = wallets.get(user_id_str, {"tokens": 0})
        balance = user_wallet.get("tokens", 0)
        if choice == result:
            new_balance = balance + self.bet_amount
            embed = discord.Embed(title=f"The coin landed on **{result.capitalize()}**!", description=f" You won! **{self.bet_amount}** Tokens have been added to your wallet.", color=discord.Color.green())
        else:
            new_balance = balance - self.bet_amount
            embed = discord.Embed(title=f"The coin landed on **{result.capitalize()}**!", description=f"Mr. Zebzoub, you lost! **{self.bet_amount}** Tokens have been removed from your wallet.", color=discord.Color.red())
        embed.set_author(name=f"{self.author.display_name}'s Coin Flip")
        embed.add_field(name="New Balance", value=f" **{new_balance}** Tokens")
        if self.author.avatar:
            embed.set_thumbnail(url=self.author.avatar.url)
        user_wallet["tokens"] = new_balance
        wallets[user_id_str] = user_wallet
        save_data(wallets, resolve_filepath(PLAYER_WALLETS_FILE))
        await interaction.response.edit_message(content=f"{self.author.mention}, the result is in!", embed=embed, view=self)

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary, emoji="🪙")
    async def heads_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "heads"
        await self.handle_flip(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary, emoji="⚪")
    async def tails_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "tails"
        await self.handle_flip(interaction, "tails")

    async def on_timeout(self):
        if self.result_message:
            for item in self.children:
                item.disabled = True
            await self.result_message.edit(content="This coin flip has expired.", view=self)

class DoubleOrNothingView(discord.ui.View):
    def __init__(self, author: discord.Member, points_won: int, original_interaction: discord.Interaction):
        super().__init__(timeout=60.0)
        self.author = author
        self.points_won = points_won
        self.original_interaction = original_interaction
        self.clicked = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your bet to double!", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Double or Nothing?", style=discord.ButtonStyle.success, emoji="")
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.clicked = True
        for item in self.children:
            item.disabled = True
        self.stop()
        result = random.choice([True, False])
        user_id_str = str(self.author.id)
        player_stats = load_data(resolve_filepath(PLAYER_STATS_FILE))
        user_stats = player_stats.get(user_id_str, {})
        user_stats["bonus_points"] = user_stats.get("bonus_points", 0)
        if result: # WIN
            user_stats["bonus_points"] += self.points_won
            await interaction.response.send_message(f"**You won the flip!** Your point gain was doubled to **{self.points_won * 2}** points for that roll!")
        else: # LOSS
            user_stats["bonus_points"] -= self.points_won
            await interaction.response.send_message(f"**You lost the flip!** You lose the **{self.points_won}** points you just gained from that roll.")
        player_stats[user_id_str] = user_stats
        save_data(player_stats, resolve_filepath(PLAYER_STATS_FILE))
        await self.original_interaction.edit_original_response(view=self)

    async def on_timeout(self):
        if not self.clicked and self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

class GoonerModeConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=30.0)
        self.author = author
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This is not your decision!", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        user_id_str = str(self.author.id)
        player_stats = load_data(resolve_filepath(PLAYER_STATS_FILE))
        user_stats = player_stats.get(user_id_str, {})
        user_stats["gooner_mode_active"] = True
        player_stats[user_id_str] = user_stats
        save_data(player_stats, resolve_filepath(PLAYER_STATS_FILE))
        final_view = discord.ui.View(timeout=None)
        final_view.add_item(discord.ui.Button(label="Roll from the Main Panel!", style=discord.ButtonStyle.danger, emoji="🎰", disabled=True))
        await interaction.response.edit_message(content="**Gooner Mode is now ACTIVE!** Now presss **'Try Your Luck!'**", view=final_view)
        self.stop()
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Gooner Mode activation cancelled.", view=None)
        self.stop()

class RandomRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Try Your Luck!", style=discord.ButtonStyle.danger, emoji="🎰", custom_id="random_role_button")
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.user
            user_id_str = str(user.id)
            
            game_state = load_data(GAME_STATE_FILE)
            is_dev_mode = game_state.get("dev_mode", False)

            active_event, _ = get_active_event()
            event_info = EVENT_CONFIG.get(active_event) if active_event else None
            
            upgrades = load_data(resolve_filepath(PLAYER_UPGRADES_FILE)).get(user_id_str, {})
            cooldown_reduction = upgrades.get("has_second_roll", False)
            
            current_cooldown = COOLDOWN_HOURS / 2 if cooldown_reduction else COOLDOWN_HOURS
            if event_info and event_info['modifier_type'] == 'cooldown_reduction':
                current_cooldown = event_info['value']
            
            cooldowns = load_data(resolve_filepath(COOLDOWN_FILE))
            if not (is_dev_mode and user.id in ADMIN_USER_IDS) and user_id_str in cooldowns:
                last_press_time = datetime.fromisoformat(cooldowns[user_id_str])
                if datetime.now() < last_press_time + timedelta(hours=current_cooldown):
                    remaining_time = (last_press_time + timedelta(hours=current_cooldown)) - datetime.now()
                    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                    minutes, _ = divmod(remainder, 60)
                    await interaction.response.send_message(f"You're on cooldown! Please wait another **{int(hours)} hours and {int(minutes)} minutes**.", ephemeral=True)
                    return
            
            await interaction.response.defer(ephemeral=False, thinking=True)
            
            inventories = load_data(resolve_filepath(PLAYER_INVENTORIES_FILE))
            player_stats = load_data(resolve_filepath(PLAYER_STATS_FILE))
            user_inventory = inventories.get(user_id_str, {"active_items": {}})
            user_stats = player_stats.get(user_id_str, {"display_name": user.display_name, "roles": {n: 0 for n in ROLE_CONFIG.keys()}, "streak": 0, "last_play_timestamp": None, "gooner_mode_active": False, "bonus_points": 0})
            event_messages = []

            is_gooner_mode = user_stats.get("gooner_mode_active", False)
            point_multiplier = 2.0 if is_gooner_mode else 1.0
            if event_info and event_info['modifier_type'] == 'point_multiplier':
                point_multiplier *= event_info['value']
            
            token_multiplier = event_info['value'] if event_info and event_info['modifier_type'] == 'token_multiplier' else 1.0

            if is_gooner_mode:
                event_messages.append("‼️ **[GOONER MODE ROLL]** ‼️")

            standard_role_ids = {v['id'] for k, v in ROLE_CONFIG.items() if k != "MRBAB"}
            roles_to_remove = [role for role in user.roles if role.id in standard_role_ids]
            if roles_to_remove: await user.remove_roles(*roles_to_remove, reason="Daily role swap")

            def perform_roll():
                gs = load_data(resolve_filepath(GAME_STATE_FILE))
                psj = gs.get("plays_since_jackpot", 0)
                pity_multiplier = event_info['value'] if event_info and event_info['modifier_type'] == 'mrbab_pity_multiplier' else 1.0
                cmw = ROLE_CONFIG["MRBAB"]["weight"] + (psj * MRBAB_WEIGHT_INCREASE * pity_multiplier)
                wtr = cmw - ROLE_CONFIG["MRBAB"]["weight"]
                oroles = [r for r in ROLE_CONFIG if r != "MRBAB"]
                lpr = wtr / len(oroles) if oroles else 0
                dw = {rn: (cmw if rn == "MRBAB" else max(1, cfg["weight"] - lpr)) for rn, cfg in ROLE_CONFIG.items()}
                
                luck_tweak_tier = upgrades.get("luck_tweak_tier", 0)
                if luck_tweak_tier > 0:
                    for r in dw:
                        if ROLE_CONFIG[r]['points'] > 0: dw[r] *= (1 + (luck_tweak_tier * 0.02))

                if event_info:
                    mod_type, value = event_info['modifier_type'], event_info['value']
                    if mod_type == 'weight_boost_positive':
                        for r in dw:
                            if ROLE_CONFIG[r]['points'] > 0: dw[r] *= value
                    elif mod_type == 'weight_boost_negative':
                        for r in dw:
                            if ROLE_CONFIG[r]['points'] < 0: dw[r] *= value
                    elif mod_type == 'randomize_all':
                        for r in dw: dw[r] = random.randint(1, 250)
                tw = sum(dw.values())
                rnum = random.uniform(1, tw)
                crn, cw = None, 0
                for role_name, weight in sorted(dw.items()):
                    cw += weight
                    if rnum <= cw:
                        crn = role_name
                        break
                return crn or "NPC", rnum, tw, dw, tw

            chosen_role_name, rolled_number, total_weight, final_weights, final_total_weight = perform_roll()
            
            if chosen_role_name == "Na9ch" and user_inventory.get("active_items", {}).get("safety_net", 0) > 0:
                original_role = chosen_role_name
                chosen_role_name = "NPC"
                user_inventory["active_items"]["safety_net"] -= 1
                event_messages.append(f"🛡️ Your **Safety Net** was used, saving you from '{original_role}' and giving you '{chosen_role_name}' instead!")
            elif ROLE_CONFIG[chosen_role_name]['points'] < 0 and user_inventory.get("active_items", {}).get("lucky_clover", 0) > 0:
                user_inventory["active_items"]["lucky_clover"] -= 1
                if random.random() < 0.25:
                    event_messages.append(f"🍀 Your **Lucky Clover** activated! You can re-roll")
                    chosen_role_name, rolled_number, total_weight, final_weights, final_total_weight = perform_roll()
                else:
                    event_messages.append(f"🍀 You used your Lucky Clover, but luck wasn't on your side this time.")

            inventories[user_id_str] = user_inventory
            save_data(inventories, resolve_filepath(PLAYER_INVENTORIES_FILE))

            role_to_add = interaction.guild.get_role(ROLE_CONFIG[chosen_role_name]['id'])
            if role_to_add:
                await user.add_roles(role_to_add, reason="Daily random role assignment")
                cooldowns[user_id_str] = datetime.now().isoformat()
                save_data(cooldowns, resolve_filepath(COOLDOWN_FILE))

                user_stats["display_name"] = user.display_name
                user_stats["roles"][chosen_role_name] = user_stats["roles"].get(chosen_role_name, 0) + 1
                total_plays = sum(user_stats["roles"].values())

                now = datetime.now()
                streak_broken = True
                if user_stats.get("last_play_timestamp"):
                    last_play = datetime.fromisoformat(user_stats["last_play_timestamp"])
                    if (now - last_play) < timedelta(hours=current_cooldown * 2):
                        user_stats["streak"] = user_stats.get("streak", 0) + 1
                        streak_broken = False
                
                if streak_broken: user_stats["streak"] = 1
                user_stats["last_play_timestamp"] = now.isoformat()
                if is_gooner_mode: user_stats["gooner_mode_active"] = False

                bonus_tokens = 0
                if user_stats["streak"] in STREAK_REWARDS:
                    reward_info = STREAK_REWARDS[user_stats["streak"]]
                    bonus_tokens += reward_info["tokens"]
                    event_messages.append(reward_info["message"])
                if total_plays in PLAY_MILESTONES:
                    reward_info = PLAY_MILESTONES[total_plays]
                    bonus_tokens += reward_info["tokens"]
                    event_messages.append(reward_info["message"])
                
                if "bonus_points" not in user_stats:
                    user_stats["bonus_points"] = 0

                base_points = ROLE_CONFIG[chosen_role_name]['points']
                if chosen_role_name == "MRBAB":
                    mrbab_chance = (final_weights['MRBAB'] / final_total_weight) * 100
                    base_points = max(5, int(20 - (mrbab_chance * 3)))
                
                final_points_for_roll = int(base_points * point_multiplier)
                
                if event_info and event_info['modifier_type'] == 'invert_points' and chosen_role_name != "MRBAB":
                    final_points_for_roll *= -1

                user_stats["bonus_points"] += (final_points_for_roll - base_points)

                player_stats[user_id_str] = user_stats
                save_data(player_stats, resolve_filepath(PLAYER_STATS_FILE))
                
                expirations = load_data(resolve_filepath(ROLE_EXPIRATIONS_FILE))
                exp_time = now + (timedelta(days=7) if chosen_role_name == "MRBAB" else timedelta(hours=current_cooldown))
                expirations.append({"user_id": user_id_str, "role_id": role_to_add.id, "expiration_time": exp_time.isoformat()})
                save_data(expirations, resolve_filepath(ROLE_EXPIRATIONS_FILE))

                wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
                user_wallet = wallets.get(user_id_str, {"tokens": 0})
                base_reward = int(TOKEN_REWARDS.get(chosen_role_name, 0) * token_multiplier)
                total_reward = base_reward + bonus_tokens
                user_wallet["tokens"] = user_wallet.get("tokens", 0) + total_reward
                wallets[user_id_str] = user_wallet
                save_data(wallets, resolve_filepath(PLAYER_WALLETS_FILE))

                final_message_parts = [f"You rolled a **{rolled_number:.2f}** (out of {total_weight:.2f})!\nRigelha {user.mention}! Rak **{role_to_add.name}** lyoum!"]
                if event_messages: final_message_parts.extend(event_messages)
                final_message_parts.append(f"You earned **{total_reward}** Tokens!")
                final_response = "\n\n".join(final_message_parts)
                
                current_game_state = load_data(resolve_filepath(GAME_STATE_FILE))
                
                view_to_send = None
                if final_points_for_roll > 0 and random.random() < 0.05:
                    view_to_send = DoubleOrNothingView(author=user, points_won=final_points_for_roll, original_interaction=interaction)

                if chosen_role_name == "MRBAB":
                    current_game_state["plays_since_jackpot"] = 0
                    jackpot_embed = discord.Embed(title="🎰🎰🎰  J A C K P O T  🎰🎰🎰", description=final_response.replace(f"Rigelha {user.mention}! Rak **{role_to_add.name}** lyoum!", f"Congratulations to our new MRBAB, {user.mention}!"), color=discord.Color.gold())
                    if view_to_send:
                        message = await interaction.followup.send("@everyone", embed=jackpot_embed, view=view_to_send, wait=True)
                        view_to_send.message = message
                    else:
                        await interaction.followup.send("@everyone", embed=jackpot_embed)
                else:
                    current_game_state["plays_since_jackpot"] = current_game_state.get("plays_since_jackpot", 0) + 1
                    if view_to_send:
                        message = await interaction.followup.send(final_response, view=view_to_send, wait=True)
                        view_to_send.message = message
                    else:
                        await interaction.followup.send(final_response)

                save_data(current_game_state, resolve_filepath(GAME_STATE_FILE))
            else:
                await interaction.followup.send("Error: Could not find the role.", ephemeral=True)
        except Exception as e:
            print(f"Error in button callback: {e}")
            traceback.print_exc()
            await interaction.followup.send("A critical error occurred.", ephemeral=True)

    @discord.ui.button(label="Gooner Mode", style=discord.ButtonStyle.secondary, emoji="🔥", custom_id="gooner_mode_button")
    async def gooner_mode_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        player_stats = load_data(resolve_filepath(PLAYER_STATS_FILE))
        user_stats = player_stats.get(str(user.id), {})

        if user_stats.get("gooner_mode_active", False):
            await interaction.response.send_message("Gooner Mode is already active for your next roll.", ephemeral=True)
            return

        view = GoonerModeConfirmView(author=user)
        await interaction.response.send_message(
            "**Activate Gooner Mode?**\n"
            "Your next roll's point rewards and losses will be **doubled**. This action is permanent for your next roll.",
            view=view,
            ephemeral=True
        )

# --- BACKGROUND TASKS & OTHER FUNCTIONS ---
@tasks.loop(minutes=1)
async def check_role_expirations():
    await bot.wait_until_ready()
    now = datetime.now()
    all_expirations = load_data(resolve_filepath(ROLE_EXPIRATIONS_FILE))
    still_active_expirations = []
    if not all_expirations: return
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    for record in all_expirations:
        expire_time = datetime.fromisoformat(record["expiration_time"])
        if now >= expire_time:
            user_id, role_id = int(record["user_id"]), int(record["role_id"])
            try:
                member = await guild.fetch_member(user_id)
                role_to_remove = guild.get_role(role_id)
                if member and role_to_remove:
                    await member.remove_roles(role_to_remove, reason="Gambling role expired")
            except discord.NotFound: pass
            except discord.Forbidden: print(f"ERROR: Missing permissions to remove role from member {user_id}.")
            except discord.HTTPException as e: print(f"ERROR: Failed to remove role. {e}")
        else:
            still_active_expirations.append(record)
    save_data(still_active_expirations, resolve_filepath(ROLE_EXPIRATIONS_FILE))

@tasks.loop(hours=24)
async def daily_board_post():
    await bot.wait_until_ready()
    guild, channel = bot.get_guild(GUILD_ID), bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel and guild: await channel.send(f"**Leaderboard Update for {datetime.now().strftime('%Y-%m-%d')}**", embed=generate_leaderboard_embed(guild))
    else: print(f"Error: Could not find channel ({LEADERBOARD_CHANNEL_ID}) or guild ({GUILD_ID}).")

@daily_board_post.before_loop
async def before_daily_post():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    target_time = time(0, 0, 0, tzinfo=timezone.utc)
    next_run = datetime.combine(now.date(), target_time)
    if now.time() > target_time: 
        next_run += timedelta(days=1)
    await asyncio.sleep((next_run - now).total_seconds())

def generate_weekly_highlights_embed():
    weekly_stats = load_data(resolve_filepath(WEEKLY_STATS_FILE))
    if not weekly_stats: return None
    embed = discord.Embed(title=" Weekly Gambling Report ", description="Here are the highlights from the past week!", color=discord.Color.blue())
    embed.set_thumbnail(url="https://neurosciencenews.com/files/2020/02/slot-machine-vision-sound-neurosciennewws-public.jpg")
    def get_weekly_winner(role_name):
        max_count, winners = 0, []
        for user_id, data in weekly_stats.items():
            count = data["roles"].get(role_name, 0)
            if count > max_count: max_count, winners = count, [user_id]
            elif count == max_count and count > 0: winners.append(user_id)
        if not winners: return "No one! A quiet week."
        return f'{", ".join([f"<@{uid}>" for uid in winners])} (with **{max_count}** rolls)'
    embed.add_field(name="👑 MRBAB of the Week", value=get_weekly_winner("MRBAB"), inline=False)
    embed.add_field(name="💪 Rajel of the Week", value=get_weekly_winner("Rajel"), inline=False)
    embed.add_field(name="🤖 NPC of the Week", value=get_weekly_winner("NPC"), inline=False)
    embed.add_field(name="🏳️‍🌈 Gay of the Week", value=get_weekly_winner("Gay"), inline=False)
    embed.add_field(name="🤡 Na9ch of the Week", value=get_weekly_winner("Na9ch"), inline=False)
    return embed

@tasks.loop(hours=168)
async def weekly_highlights_post():
    await bot.wait_until_ready()
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel: return
    embed = generate_weekly_highlights_embed()
    if embed:
        await channel.send(embed=embed)
        save_data({}, resolve_filepath(WEEKLY_STATS_FILE))
        print("Weekly highlights posted and weekly stats have been reset.")

@weekly_highlights_post.before_loop
async def before_weekly_highlights():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc)
    target_weekday, target_time = 4, time(19, 0, 0, tzinfo=timezone.utc)
    days_until_target = (target_weekday - now.weekday() + 7) % 7
    next_run_date = now.date() + timedelta(days=days_until_target)
    next_run_datetime = datetime.combine(next_run_date, target_time)
    if now > next_run_datetime: next_run_datetime += timedelta(weeks=1)
    await asyncio.sleep((next_run_datetime - now).total_seconds())

@tasks.loop(hours=6)
async def random_event_starter():
    await bot.wait_until_ready()
    game_state = load_data(resolve_filepath(GAME_STATE_FILE))
    if game_state.get("active_event"):
        return

    if random.random() < RANDOM_EVENT_CHANCE:
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not channel: return

        event_id = random.choice(list(EVENT_CONFIG.keys()))
        event_info = EVENT_CONFIG[event_id]
        duration = random.randint(30, 120)
        
        end_time = datetime.now() + timedelta(minutes=duration)
        game_state["active_event"] = event_id
        game_state["event_end_time"] = end_time.isoformat()
        save_data(game_state, resolve_filepath(GAME_STATE_FILE))

        embed = discord.Embed(title=f"🎉 AN EVENT HAS STARTED: {event_info['name']} 🎉", description=f"{event_info['description']}\n\nThis event will last for **{duration} minutes**.", color=discord.Color.random())
        await channel.send("@everyone", embed=embed)
        print(f"Randomly started event: {event_id} for {duration} minutes.")

def generate_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    stats = load_data(resolve_filepath(PLAYER_STATS_FILE))
    embed = discord.Embed(title="Gambling Core Leaderboard", color=discord.Color.gold())
    embed.set_thumbnail(url=LEADERBOARD_IMAGE_URL)
    if not stats:
        embed.description = "The season has just begun!"
        return embed

    now = datetime.now()
    active_players = {}
    for user_id, data in stats.items():
        if data.get("last_play_timestamp"):
            last_play = datetime.fromisoformat(data["last_play_timestamp"])
            if (now - last_play) < timedelta(days=10):
                active_players[user_id] = data

    if not active_players:
        embed.description = "No players have gambled in the last 10 days. The leaderboard is waiting for new challengers!"
        return embed

    upgrades_data = load_data(resolve_filepath(PLAYER_UPGRADES_FILE))
    sorted_players = sorted(active_players.items(), key=lambda item: (sum(item[1]['roles'].get(r, 0) * ROLE_CONFIG[r]['points'] for r in item[1]['roles']) + item[1].get('bonus_points', 0)) + (sum(item[1]['roles'].values()) * (LOYALTY_WEIGHT + (0.1 if upgrades_data.get(item[0], {}).get("has_loyalty_boost") else 0))), reverse=True)
    leaderboard_string, rank = "", 1
    for user_id, data in sorted_players:
        name, roles = data['display_name'], data['roles']
        total_plays = sum(roles.values())
        base_points = sum(count * ROLE_CONFIG[role_name]['points'] for role_name, count in roles.items())
        bonus_points = data.get('bonus_points', 0)
        total_points = base_points + bonus_points
        current_loyalty_weight = LOYALTY_WEIGHT + (0.1 if upgrades_data.get(user_id, {}).get("has_loyalty_boost") else 0)
        final_score = total_points + (total_plays * current_loyalty_weight)
        jackpot, rajel, na9ch, npc, gay = roles.get("MRBAB", 0), roles.get("Rajel", 0), roles.get("Na9ch", 0), roles.get("NPC", 0), roles.get("Gay", 0)
        leaderboard_string += (f"**{rank}. {name}** — **{final_score:.2f} Score** (Points: {total_points})\n> Plays: {total_plays} | MRBAB Rolls: {jackpot}\n> `Rajel:{rajel}` `Na9ch:{na9ch}` `NPC:{npc}` `Gay:{gay}`\n--------------------\n")
        rank += 1
        if rank > 20 or len(leaderboard_string) > 3800: 
            leaderboard_string += "...and more!"
            break
    embed.description = leaderboard_string
    embed.set_footer(text=f"Only players active in the last 10 days are shown.")
    return embed

# --- BOT COMMANDS ---
@bot.command(name="help", aliases=["commands"], help="Shows this help message.")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(title="Rigelha Gambling Bot Help", description="Here is a list of all available commands. Commands are case-insensitive.", color=discord.Color.blurple())
    player_cmds, admin_cmds = {}, {}
    for command in bot.commands:
        if command.name == "help": continue
        aliases = f" (aliases: {', '.join(command.aliases)})" if command.aliases else ""
        cmd_string = f"**!{command.name}**{aliases}\n> {command.help or 'No description available.'}\n"
        if command.checks:
            admin_cmds[command.name] = cmd_string
        else:
            player_cmds[command.name] = cmd_string
    if player_cmds:
        player_cmds_text = "".join(player_cmds[key] for key in sorted(player_cmds.keys()))
        embed.add_field(name=" Player Commands", value=player_cmds_text, inline=False)
    if admin_cmds and ctx.author.id in ADMIN_USER_IDS:
        admin_cmds_text = "".join(admin_cmds[key] for key in sorted(admin_cmds.keys()))
        embed.add_field(name=" Admin Commands", value=admin_cmds_text, inline=False)
    embed.set_footer(text="Good luck, gambler!")
    await ctx.send(embed=embed)

@bot.command(name="board", help="Displays the server-wide gambling leaderboard.")
async def board(ctx: commands.Context):
    await ctx.send(embed=generate_leaderboard_embed(ctx.guild))

@bot.command(name="rigl", help="Posts the main gambling panel.")
@commands.has_permissions(administrator=False)
async def setup_role_panel(ctx: commands.Context):
    await ctx.send("## 🎲 Are you ready ?\n\n", view=RandomRoleView())

@setup_role_panel.error
async def setup_panel_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("This command is restricted to administrators.")

@bot.command(name="chances", help="Shows the current gambling odds and roll ranges.")
async def chances(ctx: commands.Context):
    try:
        game_state = load_data(resolve_filepath(GAME_STATE_FILE))
        upgrades = load_data(resolve_filepath(PLAYER_UPGRADES_FILE)).get(str(ctx.author.id), {})
        plays_since_jackpot = game_state.get("plays_since_jackpot", 0)
        active_event, _ = get_active_event()
        event_info = EVENT_CONFIG.get(active_event) if active_event else None
        pity_multiplier = event_info['value'] if event_info and event_info['modifier_type'] == 'mrbab_pity_multiplier' else 1.0
        current_mrbab_weight = ROLE_CONFIG["MRBAB"]["weight"] + (plays_since_jackpot * MRBAB_WEIGHT_INCREASE * pity_multiplier)
        weight_to_remove = current_mrbab_weight - ROLE_CONFIG["MRBAB"]["weight"]
        other_roles = [r for r in ROLE_CONFIG if r != "MRBAB"]
        loss_per_role = weight_to_remove / len(other_roles) if other_roles else 0
        dynamic_weights = {rn: (current_mrbab_weight if rn == "MRBAB" else max(1, cfg["weight"] - lpr)) for rn, cfg in ROLE_CONFIG.items()}
        luck_tweak_tier = upgrades.get("luck_tweak_tier", 0)
        if luck_tweak_tier > 0:
            for r in dynamic_weights:
                if ROLE_CONFIG[r]['points'] > 0: dynamic_weights[r] *= (1 + (luck_tweak_tier * 0.02))
        if event_info:
            mod_type, value = event_info['modifier_type'], event_info['value']
            if mod_type == 'weight_boost_positive':
                for r in dynamic_weights:
                    if ROLE_CONFIG[r]['points'] > 0: dynamic_weights[r] *= value
            elif mod_type == 'weight_boost_negative':
                for r in dynamic_weights:
                    if ROLE_CONFIG[r]['points'] < 0: dynamic_weights[r] *= value
            elif mod_type == 'randomize_all':
                for r in dynamic_weights: dynamic_weights[r] = random.randint(1, 250)
        total_weight = sum(dynamic_weights.values())
        embed = discord.Embed(title="🎰 Current Gambling Odds", description=f"The system rolls a virtual die from **1 to {total_weight:.2f}**.", color=discord.Color.dark_purple())
        if event_info:
            embed.description += f"\n\n**🎉 ACTIVE EVENT: {event_info['name']}!**\n*{event_info['description']}*"
        chances_string, current_range_start = "", 1
        for role_name, weight in sorted(dynamic_weights.items()):
            percentage = (weight / total_weight) * 100
            range_end = current_range_start + weight - 1
            chances_string += f"**{role_name}**: `{percentage:.4f}%`\n> Roll Range: **{current_range_start:.2f} - {range_end:.2f}** (Weight: {weight:.2f})\n"
            current_range_start = range_end + 1
        embed.add_field(name="Role Probabilities & Ranges", value=chances_string, inline=False)
        embed.set_footer(text=f"The jackpot 'pity system' is currently at +{plays_since_jackpot} plays.")
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in !chances command: {e}")
        await ctx.send("An error occurred while calculating the chances.")

@bot.command(name="mystats", help="Shows your personal gambling statistics.")
async def mystats(ctx: commands.Context):
    user = ctx.author
    user_id_str = str(user.id)
    all_player_stats = load_data(resolve_filepath(PLAYER_STATS_FILE))
    upgrades = load_data(resolve_filepath(PLAYER_UPGRADES_FILE)).get(user_id_str, {})
    user_stats = all_player_stats.get(user_id_str)
    if not user_stats or not any(user_stats.get("roles", {}).values()):
        await ctx.send("You haven't tried your luck yet! Press the button to get started.")
        return
    roles_data = user_stats.get("roles", {})
    total_plays = sum(roles_data.values())
    base_points = sum(count * ROLE_CONFIG[role_name]['points'] for role_name, count in roles_data.items())
    bonus_points = user_stats.get("bonus_points", 0)
    total_points = base_points + bonus_points
    jackpots = roles_data.get("MRBAB", 0)
    wins = sum(count for role, count in roles_data.items() if ROLE_CONFIG[role]['points'] > 0)
    losses = sum(count for role, count in roles_data.items() if ROLE_CONFIG[role]['points'] < 0)
    most_rolled_role = max(roles_data, key=roles_data.get) if roles_data else "None"
    wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
    balance = wallets.get(user_id_str, {}).get("tokens", 0)
    streak = user_stats.get("streak", 0)
    
    embed_color = int(upgrades.get("mystats_color", "0x3498db")[1:], 16) if upgrades.get("mystats_color") else user.color
    embed = discord.Embed(title=f"📊 Stats for {user.display_name}", description="Here's a look at your gambling career so far.", color=embed_color)
    if user.avatar: embed.set_thumbnail(url=user.avatar.url)
    current_loyalty_weight = LOYALTY_WEIGHT + 0.1 if upgrades.get("has_loyalty_boost") else LOYALTY_WEIGHT
    embed.add_field(name="Leaderboard Score", value=f"**{total_points + (total_plays * current_loyalty_weight):.2f}**", inline=True)
    embed.add_field(name="Total Plays", value=f"**{total_plays}** rolls", inline=True)
    embed.add_field(name="Win / Loss", value=f"**{wins}** wins / **{losses}** losses\n*(Roles with > 0 points are wins)*", inline=True)
    embed.add_field(name="Jackpots Hit", value=f"👑 **{jackpots}**", inline=True)
    embed.add_field(name="Current Streak", value=f"🔥 **{streak}** days", inline=True)
    embed.add_field(name="Token Balance", value=f"💰 **{balance}**", inline=True)
    embed.set_footer(text=f"Most Common Role: {most_rolled_role}")
    await ctx.send(embed=embed)

@bot.command(name="wallet", aliases=["bal", "balance"], help="Check your or another user's token balance.")
async def wallet(ctx: commands.Context, member: discord.Member = None):
    member = member or ctx.author
    wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
    balance = wallets.get(str(member.id), {}).get("tokens", 0)
    embed = discord.Embed(title=f"💰 Wallet of {member.display_name}", color=discord.Color.gold())
    if member.avatar: embed.set_thumbnail(url=member.avatar.url)
    embed.add_field(name="Current Balance", value=f"**{balance}** Tokens")
    embed.set_footer(text="Earn more tokens by playing daily!")
    await ctx.send(embed=embed)

@bot.command(name="shop", help="Displays the items available for purchase with tokens.")
async def shop(ctx: commands.Context):
    embed = discord.Embed(title="Welcome to the Gambling Shop!", description="Use `!buy <item_name>` to purchase an item. Item names are the ones in **bold**.", color=discord.Color.green())
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3081/3081648.png")
    for item_id, item_data in SHOP_ITEMS.items():
        embed.add_field(name=f"🛒 **{item_id}** - {item_data['price']} Tokens", value=item_data['description'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="inventory", aliases=["inv"], help="Check your inventory for active items.")
async def inventory(ctx: commands.Context, member: discord.Member = None):
    member = member or ctx.author
    inventories = load_data(resolve_filepath(PLAYER_INVENTORIES_FILE))
    user_inventory = inventories.get(str(member.id), {}).get("active_items", {})
    embed = discord.Embed(title=f"🎒 Inventory of {member.display_name}", color=discord.Color.orange())
    if member.avatar: embed.set_thumbnail(url=member.avatar.url)
    if not user_inventory or all(v == 0 for v in user_inventory.values()):
        embed.description = "Your inventory is empty. Visit the `!shop` to buy items!"
    else:
        inv_string = ""
        for item_id, count in user_inventory.items():
            if count > 0:
                item_name = SHOP_ITEMS.get(item_id, {}).get("name", "Unknown Item")
                inv_string += f"**{item_name}**: {count}\n"
        embed.description = inv_string if inv_string else "Your inventory is empty."
    await ctx.send(embed=embed)

@bot.command(name="buy", help="Purchase an item from the shop.")
async def buy(ctx: commands.Context, *, item_name: str):
    user = ctx.author
    user_id_str = str(user.id)
    item_id = item_name.lower().strip()
    
    game_state = load_data(GAME_STATE_FILE)
    is_dev_mode = game_state.get("dev_mode", False)
    
    if item_id not in SHOP_ITEMS:
        await ctx.send(f"Sorry, I couldn't find an item called `{item_name}`. Check the `!shop` for the correct name.")
        return
        
    item_to_buy, price = SHOP_ITEMS[item_id], SHOP_ITEMS[item_id]["price"]
    wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
    inventories = load_data(resolve_filepath(PLAYER_INVENTORIES_FILE))
    user_wallet = wallets.get(user_id_str, {"tokens": 0})
    user_inventory = inventories.get(user_id_str, {"active_items": {}, "last_cooldown_purchase": None})
    
    if not (is_dev_mode and user.id in ADMIN_USER_IDS):
        if user_wallet.get("tokens", 0) < price:
            await ctx.send(f"You don't have enough tokens. You need {price} but only have {user_wallet.get('tokens', 0)}.")
            return
            
    if item_id == "cooldown_cooler":
        if not (is_dev_mode and user.id in ADMIN_USER_IDS):
            if user_inventory.get("last_cooldown_purchase") and datetime.now() < datetime.fromisoformat(user_inventory["last_cooldown_purchase"]) + timedelta(days=7):
                await ctx.send("You can only purchase a Cooldown Cooler once every 7 days.")
                return
        cooldowns = load_data(resolve_filepath(COOLDOWN_FILE))
        if user_id_str in cooldowns:
            del cooldowns[user_id_str]
            save_data(cooldowns, resolve_filepath(COOLDOWN_FILE))
            await ctx.send(f"✅ Your cooldown has been reset! You can play again now.")
        else:
            await ctx.send("You are not currently on cooldown, so there's nothing to reset!")
            return
        user_inventory["last_cooldown_purchase"] = datetime.now().isoformat()
    else:
        user_inventory["active_items"][item_id] = user_inventory["active_items"].get(item_id, 0) + 1
        await ctx.send(f"✅ You successfully purchased one **{item_to_buy['name']}** for {price} tokens!")
        
    if not (is_dev_mode and user.id in ADMIN_USER_IDS):
        user_wallet["tokens"] -= price
        
    wallets[user_id_str] = user_wallet
    inventories[user_id_str] = user_inventory
    save_data(wallets, resolve_filepath(PLAYER_WALLETS_FILE))
    save_data(inventories, resolve_filepath(PLAYER_INVENTORIES_FILE))

@bot.command(name="flip", aliases=["coinflip"], help="Bet tokens on a 50/50 coin flip.")
async def flip(ctx: commands.Context, amount: int):
    user = ctx.author
    user_id_str = str(user.id)

    if amount <= 0:
        await ctx.send("You must bet a positive amount of tokens.")
        return

    wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
    user_wallet = wallets.get(user_id_str, {"tokens": 0})
    balance = user_wallet.get("tokens", 0)

    if balance < amount:
        await ctx.send(f"You don't have enough tokens to bet that much! You only have **{balance}** Tokens.")
        return

    view = CoinFlipView(author=user, bet_amount=amount)
    
    initial_embed = discord.Embed(
        title="Coin Flip!",
        description=f"{user.display_name} is betting **{amount}** Tokens.\nChoose Heads or Tails.",
        color=discord.Color.blue()
    )
    message = await ctx.send(embed=initial_embed, view=view)
    view.result_message = message
    
    await view.wait()

@flip.error
async def flip_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Oops! You forgot something. **Usage:** `!flip <amount>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Please provide a valid number for the amount to bet.")
    else:
        print(f"An error occurred in !flip: {error}")
        await ctx.send("An unexpected error occurred.")

@bot.command(name="events", help="Lists all possible server-wide events.")
async def events(ctx: commands.Context):
    embed = discord.Embed(title="🎉 Possible Server-Wide Events", description="These events can be started by admins or may occur randomly!", color=discord.Color.dark_magenta())
    for event_id, event_data in EVENT_CONFIG.items():
        embed.add_field(name=f"**{event_data['name']}** (`{event_id}`)", value=event_data['description'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="workshop", help="Displays permanent, high-tier upgrades.")
async def workshop(ctx: commands.Context):
    embed = discord.Embed(title="🔧 The Gambler's Workshop", description="Purchase powerful, permanent upgrades for your account. Use `!upgrade <item_name>`.", color=discord.Color.from_rgb(139, 69, 19))
    for item_id, item_data in WORKSHOP_ITEMS.items():
        embed.add_field(name=f"🛠️ **{item_id}** - {item_data['price']} Tokens", value=item_data['description'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="upgrade", help="Purchase a permanent upgrade from the workshop.")
async def upgrade(ctx: commands.Context, item_name: str, *, details: str = None):
    user = ctx.author
    user_id_str = str(user.id)
    item_id = item_name.lower().strip()
    
    if item_id not in WORKSHOP_ITEMS:
        await ctx.send(f"Sorry, I couldn't find an upgrade called `{item_name}`. Check the `!workshop` for correct names.")
        return
        
    item_to_buy = WORKSHOP_ITEMS[item_id]
    price = item_to_buy["price"]
    
    wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
    upgrades = load_data(resolve_filepath(PLAYER_UPGRADES_FILE))
    user_wallet = wallets.get(user_id_str, {"tokens": 0})
    user_upgrades = upgrades.get(user_id_str, {})
    
    if user_wallet.get("tokens", 0) < price:
        await ctx.send(f"You can't afford this upgrade. You need **{price}** Tokens but only have **{user_wallet.get('tokens', 0)}**.")
        return

    if item_id == "luck_tweak":
        current_tier = user_upgrades.get("luck_tweak_tier", 0)
        if current_tier >= 5:
            await ctx.send("You have already maxed out this upgrade!")
            return
        user_upgrades["luck_tweak_tier"] = current_tier + 1
        await ctx.send(f"✅ **Upgrade Complete!** You purchased **{item_to_buy['name']}** (Tier {current_tier + 1}). Your positive roll luck has been permanently increased.")
    
    elif item_id == "second_roll":
        if user_upgrades.get("has_second_roll", False):
            await ctx.send("You have already purchased this powerful upgrade!")
            return
        user_upgrades["has_second_roll"] = True
        await ctx.send(f"✅ **A Monumental Achievement!** You have purchased **{item_to_buy['name']}**. Your gambling cooldown is now permanently halved!")

    elif item_id == "mystats_color":
        if not details or not (details.startswith("#") and len(details) == 7):
            await ctx.send("Please provide a valid 6-digit hex color code (e.g., `!upgrade mystats_color #FFD700`).")
            return
        try:
            int(details[1:], 16)
        except ValueError:
            await ctx.send("Invalid hex color code. Please use a format like `#RRGGBB`.")
            return
        user_upgrades["mystats_color"] = details
        await ctx.send(f"✅ **Cosmetic Upgrade Complete!** Your `!mystats` embed will now be the color `{details}`.")

    elif item_id == "loyalty_boost":
        if user_upgrades.get("has_loyalty_boost", False):
            await ctx.send("You have already purchased this upgrade!")
            return
        user_upgrades["has_loyalty_boost"] = True
        await ctx.send(f"✅ **Upgrade Complete!** You have purchased the **{item_to_buy['name']}**. Your leaderboard score will now increase faster with each play.")

    user_wallet["tokens"] -= price
    wallets[user_id_str] = user_wallet
    upgrades[user_id_str] = user_upgrades
    
    save_data(wallets, resolve_filepath(PLAYER_WALLETS_FILE))
    save_data(upgrades, resolve_filepath(PLAYER_UPGRADES_FILE))

@bot.command(name="eventstatus", aliases=["event"], help="Check the current server-wide gambling event.")
async def eventstatus(ctx: commands.Context):
    event_name, end_time = get_active_event()
    if not event_name:
        await ctx.send("There is no server-wide event currently active.")
        return
    event_info = EVENT_CONFIG.get(event_name)
    remaining_time = end_time - datetime.now()
    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    embed = discord.Embed(title=f"🎉 Active Event: {event_info['name']} 🎉", description=event_info['description'], color=discord.Color.purple())
    if hours > 0:
        embed.add_field(name="Time Remaining", value=f"**{int(hours)} hours**, **{int(minutes)} minutes**")
    else:
        embed.add_field(name="Time Remaining", value=f"**{int(minutes)} minutes**, **{int(seconds)} seconds**")
    await ctx.send(embed=embed)

@bot.command(name="devmode", help="Toggles a sandboxed development mode. (Admin only)")
@is_allowed_user()
async def devmode(ctx: commands.Context, state: str):
    state = state.lower()
    game_state = load_data(GAME_STATE_FILE)
    files_to_sandbox = [PLAYER_STATS_FILE, PLAYER_WALLETS_FILE, PLAYER_INVENTORIES_FILE, COOLDOWN_FILE, ROLE_EXPIRATIONS_FILE, WEEKLY_STATS_FILE, GAME_STATE_FILE, PLAYER_UPGRADES_FILE]
    if state in ("on", "true", "enable"):
        if game_state.get("dev_mode", False):
            await ctx.send("⚠️ Development mode is already **ON**.")
            return
        print("Creating sandbox files for dev mode...")
        for file_path in files_to_sandbox:
            dev_path = file_path.replace(".json", "_dev.json")
            try:
                shutil.copy(file_path, dev_path)
            except FileNotFoundError:
                save_data({}, dev_path)
                print(f"Original file {file_path} not found. Created empty sandbox file {dev_path}.")
        game_state["dev_mode"] = True
        save_data(game_state, GAME_STATE_FILE)
        await bot.change_presence(activity=discord.Game(name="Under Maintenance"))
        await ctx.send("✅ **Sandboxed development mode has been enabled.** All changes are now temporary. Only bot admins can use commands.")
        print("!!! DEVELOPMENT MODE ENABLED (SANDBOXED) !!!")
    elif state in ("off", "false", "disable"):
        if not game_state.get("dev_mode", False):
            await ctx.send("✅ Development mode is already **OFF**.")
            return
        game_state["dev_mode"] = False
        save_data(game_state, GAME_STATE_FILE)
        print("Deleting sandbox files...")
        for file_path in files_to_sandbox:
            dev_path = file_path.replace(".json", "_dev.json")
            try:
                if os.path.exists(dev_path):
                    os.remove(dev_path)
            except Exception as e:
                print(f"Could not remove sandbox file {dev_path}: {e}")
        await bot.change_presence(activity=None)
        await ctx.send("✅ **Development mode has been disabled.** All temporary data has been deleted. Bot is now live.")
        print("!!! DEVELOPMENT MODE DISABLED (SANDBOX CLEANED) !!!")
    else:
        await ctx.send("Invalid state. Please use `!devmode on` or `!devmode off`.")

@bot.command(name="startevent", help="Starts a server-wide event. (Admin only)")
@is_allowed_user()
async def startevent(ctx: commands.Context, event_name: str, duration_minutes: int = 60):
    event_id = event_name.lower().strip()
    if event_id not in EVENT_CONFIG:
        await ctx.send(f"Invalid event name. Valid events are: {', '.join(f'`{k}`' for k in EVENT_CONFIG.keys())}")
        return
    game_state = load_data(resolve_filepath(GAME_STATE_FILE))
    if game_state.get("active_event"):
        await ctx.send("An event is already running! Please use `!stopevent` first.")
        return
    event_info = EVENT_CONFIG[event_id]
    end_time = datetime.now() + timedelta(minutes=duration_minutes)
    game_state["active_event"] = event_id
    game_state["event_end_time"] = end_time.isoformat()
    save_data(game_state, resolve_filepath(GAME_STATE_FILE))
    embed = discord.Embed(title=f"🎉 EVENT STARTED: {event_info['name']} 🎉", description=f"{event_info['description']}\n\nThis event will last for **{duration_minutes} minutes**.", color=discord.Color.purple())
    await ctx.send("@everyone", embed=embed)

@bot.command(name="stopevent", help="Stops the current server-wide event. (Admin only)")
@is_allowed_user()
async def stopevent(ctx: commands.Context):
    game_state = load_data(resolve_filepath(GAME_STATE_FILE))
    if "active_event" in game_state:
        event_name = game_state.get("active_event")
        event_info = EVENT_CONFIG.get(event_name, {"name": "Unknown Event"})
        del game_state["active_event"]
        if "event_end_time" in game_state: del game_state["event_end_time"]
        save_data(game_state, resolve_filepath(GAME_STATE_FILE))
        await ctx.send(f"✅ The **{event_info['name']}** event has been manually stopped.")
    else:
        await ctx.send("There is no event currently active to stop.")

@bot.command(name="adjusttokens", aliases=["modtokens"], help="Adds or removes tokens from a user's wallet. (Admin only)")
@is_allowed_user()
async def adjusttokens(ctx: commands.Context, member: discord.Member, amount: int):
    user_id_str = str(member.id)
    wallets = load_data(resolve_filepath(PLAYER_WALLETS_FILE))
    user_wallet = wallets.get(user_id_str, {"tokens": 0})
    new_balance = max(0, user_wallet.get("tokens", 0) + amount)
    user_wallet["tokens"] = new_balance
    wallets[user_id_str] = user_wallet
    save_data(wallets, resolve_filepath(PLAYER_WALLETS_FILE))
    action = "Added" if amount >= 0 else "Removed"
    await ctx.send(f"✅ Successfully {action} **{abs(amount)}** tokens for **{member.display_name}**. Their new balance is **{new_balance}**.")

@bot.command(name="resetcooldown", aliases=["resetcd"], help="Resets a user's gambling cooldown. (Admin only)")
@is_allowed_user()
async def resetcooldown(ctx: commands.Context, member: discord.Member):
    user_id_str = str(member.id)
    cooldowns = load_data(resolve_filepath(COOLDOWN_FILE))
    if user_id_str in cooldowns:
        del cooldowns[user_id_str]
        save_data(cooldowns, resolve_filepath(COOLDOWN_FILE))
        await ctx.send(f"✅ Cooldown for **{member.display_name}** has been reset. They can play again now.")
    else:
        await ctx.send(f"**{member.display_name}** is not currently on cooldown.")
        
@bot.command(name="giveitem", help="Gives a shop item to a user. (Admin only)")
@is_allowed_user()
async def giveitem(ctx: commands.Context, member: discord.Member, item_id: str, amount: int = 1):
    item_id = item_id.lower().strip()
    if item_id not in SHOP_ITEMS:
        await ctx.send(f"Error: `{item_id}` is not a valid item ID. Check the `!shop` for correct names.")
        return
    user_id_str = str(member.id)
    inventories = load_data(resolve_filepath(PLAYER_INVENTORIES_FILE))
    user_inventory = inventories.get(user_id_str, {"active_items": {}})
    user_inventory["active_items"][item_id] = user_inventory["active_items"].get(item_id, 0) + amount
    inventories[user_id_str] = user_inventory
    save_data(inventories, resolve_filepath(PLAYER_INVENTORIES_FILE))
    item_name = SHOP_ITEMS[item_id]["name"]
    await ctx.send(f"✅ Gave **{amount}x {item_name}** to **{member.display_name}**.")

@bot.command(name="weeklyreport", help="Manually generates the weekly highlights report. (Admin only)")
@is_allowed_user()
async def weeklyreport(ctx: commands.Context):
    embed = generate_weekly_highlights_embed()
    if embed: await ctx.send("Here is the current weekly report preview:", embed=embed)
    else: await ctx.send("There is no data for the current week to report on.")

@weeklyreport.error
async def weeklyreport_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure): await ctx.send("You do not have permission to use this command.")

@bot.command(name="shutdown", help="Shuts down the bot. (Admin only)")
@is_allowed_user()
async def shutdown(ctx: commands.Context):
    await ctx.send("Bot is shutting down..."); print("Shutdown command received. Closing bot connection...")
    await bot.close(); print("Bot connection closed. Exiting process.")
    sys.exit()

@shutdown.error
async def shutdown_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure): await ctx.send("You do not have permission to use this command.")

# --- RUN THE BOT ---
#keep_alive()
bot.run(TOKEN)