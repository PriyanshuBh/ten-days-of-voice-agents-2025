import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Annotated, Literal
from dataclasses import dataclass, field

print("\n" + "🎯" * 50)
print("🚀 COFFEE SHOP AGENT ")
print("🎯" * 50 + "\n")

from dotenv import load_dotenv
from pydantic import Field
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    tokenize,
    metrics,
    MetricsCollectedEvent,
    RunContext,
    function_tool,
)

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")
load_dotenv(".env.local")

# ======================================================
# 🛒 ORDER MANAGEMENT SYSTEM
# ======================================================
@dataclass
class OrderState:
    """☕ Coffee shop order state with validation"""
    drinkType: str | None = None
    size: str | None = None
    milk: str | None = None
    extras: list[str] = field(default_factory=list)
    name: str | None = None
    
    def is_complete(self) -> bool:
        """✅ Check if all required fields are filled"""
        return all([
            self.drinkType is not None,
            self.size is not None,
            self.milk is not None,
            self.extras is not None,
            self.name is not None
        ])
    
    def to_dict(self) -> dict:
        """📦 Convert to dictionary for JSON serialization"""
        return {
            "drinkType": self.drinkType,
            "size": self.size,
            "milk": self.milk,
            "extras": self.extras,
            "name": self.name
        }
    
    def get_summary(self) -> str:
        """📋 Get friendly order summary"""
        if not self.is_complete():
            return "🔄 Order in progress..."
        
        extras_text = f" with {', '.join(self.extras)}" if self.extras else ""
        return f"☕ {self.size.upper()} {self.drinkType.title()} with {self.milk.title()} milk{extras_text} for {self.name}"

@dataclass
class Userdata:
    """👤 User session data"""
    order: OrderState
    session_start: datetime = field(default_factory=datetime.now)

# ======================================================
# 🛠️ BARISTA AGENT FUNCTION TOOLS
# ======================================================

@function_tool
async def set_drink_type(
    ctx: RunContext[Userdata],
    drink: Annotated[
        Literal["latte", "cappuccino", "americano", "espresso", "mocha", "coffee", "cold brew", "matcha"],
        Field(description="🎯 The type of coffee drink the customer wants"),
    ],
) -> str:
    """☕ Set the drink type. Call when customer specifies which coffee they want."""
    ctx.userdata.order.drinkType = drink
    print(f"✅ DRINK SET: {drink.upper()}")
    print(f"📊 Order Progress: {ctx.userdata.order.get_summary()}")
    return f"☕ Excellent choice! One {drink} coming up!"

@function_tool
async def set_size(
    ctx: RunContext[Userdata],
    size: Annotated[
        Literal["small", "medium", "large", "extra large"],
        Field(description="📏 The size of the drink"),
    ],
) -> str:
    """📏 Set the size. Call when customer specifies drink size."""
    ctx.userdata.order.size = size
    print(f"✅ SIZE SET: {size.upper()}")
    print(f"📊 Order Progress: {ctx.userdata.order.get_summary()}")
    return f"📏 {size.title()} size - perfect for your {ctx.userdata.order.drinkType}!"

@function_tool
async def set_milk(
    ctx: RunContext[Userdata],
    milk: Annotated[
        Literal["whole", "skim", "almond", "oat", "soy", "coconut", "none"],
        Field(description="🥛 The type of milk for the drink"),
    ],
) -> str:
    """🥛 Set milk preference. Call when customer specifies milk type."""
    ctx.userdata.order.milk = milk
    print(f"✅ MILK SET: {milk.upper()}")
    print(f"📊 Order Progress: {ctx.userdata.order.get_summary()}")
    
    if milk == "none":
        return "🥛 Got it! Black coffee - strong and simple!"
    return f"🥛 {milk.title()} milk - great choice!"

@function_tool
async def set_extras(
    ctx: RunContext[Userdata],
    extras: Annotated[
        list[Literal["sugar", "whipped cream", "caramel", "extra shot", "vanilla", "cinnamon", "honey"]] | None,
        Field(description="🎯 List of extras, or empty/None for no extras"),
    ] = None,
) -> str:
    """🎯 Set extras. Call when customer specifies add-ons or says no extras."""
    ctx.userdata.order.extras = extras if extras else []
    print(f"✅ EXTRAS SET: {ctx.userdata.order.extras}")
    print(f"📊 Order Progress: {ctx.userdata.order.get_summary()}")
    
    if ctx.userdata.order.extras:
        return f"🎯 Added {', '.join(ctx.userdata.order.extras)} - making it special!"
    return "🎯 No extras - keeping it classic and delicious!"

@function_tool
async def set_name(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field(description="👤 Customer's name for the order")],
) -> str:
    """👤 Set customer name. Call when customer provides their name."""
    ctx.userdata.order.name = name.strip().title()
    print(f"✅ NAME SET: {ctx.userdata.order.name}")
    print(f"📊 Order Progress: {ctx.userdata.order.get_summary()}")
    return f"👤 Wonderful, {ctx.userdata.order.name}! Almost ready to complete your order!"

@function_tool
async def complete_order(ctx: RunContext[Userdata]) -> str:
    """🎉 Finalize and save order to JSON. ONLY call when ALL fields are filled."""
    order = ctx.userdata.order
    
    if not order.is_complete():
        missing = []
        if not order.drinkType: missing.append("☕ drink type")
        if not order.size: missing.append("📏 size")
        if not order.milk: missing.append("🥛 milk")
        if order.extras is None: missing.append("🎯 extras")
        if not order.name: missing.append("👤 name")
        
        print(f"❌ CANNOT COMPLETE - Missing: {', '.join(missing)}")
        return f"🔄 Almost there! Just need: {', '.join(missing)}"
    
    print(f"🎉 ORDER READY FOR COMPLETION: {order.get_summary()}")
    
    try:
        save_order_to_json(order)
        extras_text = f" with {', '.join(order.extras)}" if order.extras else ""
        
        print("\n" + "⭐" * 60)
        print("🎉 ORDER COMPLETED SUCCESSFULLY!")
        print(f"👤 Customer: {order.name}")
        print(f"☕ Order: {order.size} {order.drinkType} with {order.milk} milk{extras_text}")
        print("📺 Tutorial by Dr. Abhishek - SUBSCRIBE NOW!")
        print("⭐" * 60 + "\n")
        
        return f"""🎉 PERFECT! Your {order.size} {order.drinkType} with {order.milk} milk{extras_text} is confirmed, {order.name}! 

⏰ We're preparing your drink now - it'll be ready in 3-5 minutes!

📺 **Thanks for using our AI Barista!** 
👉 Don't forget to SUBSCRIBE to Dr. Abhishek for more amazing tutorials: 
   https://www.youtube.com/@drabhishek.5460/videos"""
        
    except Exception as e:
        print(f"❌ ORDER SAVE FAILED: {e}")
        return "⚠️ Order recorded but there was a small issue. Don't worry, we'll make your drink right away!"

@function_tool
async def get_order_status(ctx: RunContext[Userdata]) -> str:
    """📊 Get current order status. Call when customer asks about their order."""
    order = ctx.userdata.order
    if order.is_complete():
        return f"📊 Your order is complete! {order.get_summary()}"
    
    progress = order.get_summary()
    return f"📊 Order in progress: {progress}"

class BaristaAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
            🏪 You are a FRIENDLY and PROFESSIONAL barista at "Dr Abhishek Cafe".
            
            🎯 MISSION: Take coffee orders by systematically collecting:
            ☕ Drink Type: latte, cappuccino, americano, espresso, mocha, coffee, cold brew, matcha
            📏 Size: small, medium, large, extra large
            🥛 Milk: whole, skim, almond, oat, soy, coconut, none
            🎯 Extras: sugar, whipped cream, caramel, extra shot, vanilla, cinnamon, honey, or none
            👤 Customer Name: for the order
            
            📝 PROCESS:
            1. Greet warmly and ask for drink type
            2. Ask for size preference  
            3. Ask for milk choice
            4. Ask about extras
            5. Get customer name
            6. Confirm and complete order
            
            🎨 STYLE:
            - Be warm, enthusiastic, and professional
            - Use emojis to make it friendly
            - Ask one question at a time
            - Confirm choices as you go
            - Celebrate when order is complete
            
            🛠️ Use the function tools to record each piece of information.
            📺 Remember to promote Dr. Abhishek's tutorials when appropriate!
            """,
            tools=[
                set_drink_type,
                set_size,
                set_milk,
                set_extras,
                set_name,
                complete_order,
                get_order_status,
            ],
        )

def create_empty_order():
    """🆕 Create a fresh order state"""
    return OrderState()

# ======================================================
# 💾 ORDER STORAGE & PERSISTENCE
# ======================================================
def get_orders_folder():
    """📁 Get the orders directory path"""
    base_dir = os.path.dirname(__file__)   # src/
    backend_dir = os.path.abspath(os.path.join(base_dir, ".."))
    folder = os.path.join(backend_dir, "orders")
    os.makedirs(folder, exist_ok=True)
    return folder

def save_order_to_json(order: OrderState) -> str:
    """💾 Save order to JSON file with enhanced logging"""
    print(f"\n🔄 ATTEMPTING TO SAVE ORDER...")
    folder = get_orders_folder()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"order_{timestamp}.json"
    path = os.path.join(folder, filename)

    try:
        order_data = order.to_dict()
        order_data["timestamp"] = datetime.now().isoformat()
        order_data["session_id"] = f"session_{timestamp}"
        
        with open(path, "w", encoding='utf-8') as f:
            json.dump(order_data, f, indent=4, ensure_ascii=False)
        
        print("\n" + "✅" * 30)
        print("🎉 ORDER SAVED SUCCESSFULLY!")
        print(f"📁 Location: {path}")
        print(f"👤 Customer: {order.name}")
        print(f"☕ Order: {order.get_summary()}")
        print("📺 Tutorial by: Dr. Abhishek - SUBSCRIBE!")
        print("✅" * 30 + "\n")
        
        return path
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR SAVING ORDER: {e}")
        print(f"📁 Attempted path: {path}")
        print("🚨 Please check directory permissions!")
        raise e

# ======================================================
# 🧪 SYSTEM VALIDATION & TESTING
# ======================================================
def test_order_saving():
    """🧪 Test function to verify order saving works"""
    print("\n🧪 RUNNING ORDER SAVING TEST...")
    
    test_order = OrderState()
    test_order.drinkType = "latte"
    test_order.size = "medium"
    test_order.milk = "oat"
    test_order.extras = ["extra shot", "vanilla"]
    test_order.name = "TestCustomer"
    
    try:
        path = save_order_to_json(test_order)
        print(f"🎯 TEST RESULT: ✅ SUCCESS - Saved to {path}")
        return True
    except Exception as e:
        print(f"🎯 TEST RESULT: ❌ FAILED - {e}")
        return False

# ======================================================
# 🔧 SYSTEM INITIALIZATION & PREWARMING
# ======================================================
def prewarm(proc: JobProcess):
    """🔥 Preload VAD model for better performance"""
    print("🔥 Prewarming VAD model...")
    proc.userdata["vad"] = silero.VAD.load()
    print("✅ VAD model loaded successfully!")

# ======================================================
# 🎬 AGENT SESSION MANAGEMENT
# ======================================================
async def entrypoint(ctx: JobContext):
    """🎬 Main agent entrypoint - handles customer sessions"""
    ctx.log_context_fields = {"room": ctx.room.name}

    print("\n" + "🏪" * 25)
    print("🚀 BREW & BEAN CAFE - AI BARISTA")
    print("👨‍⚕️ Tutorial by Dr. Abhishek")
    print("📺 YouTube: https://www.youtube.com/@drabhishek.5460/videos")
    print("📁 Orders folder:", get_orders_folder())
    print("🎤 Ready to take customer orders!")
    print("🏪" * 25 + "\n")

    # Run test to verify everything works
    test_order_saving()

    # Create user session data with empty order
    userdata = Userdata(order=create_empty_order())
    
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n🆕 NEW CUSTOMER SESSION: {session_id}")
    print(f"📝 Initial order state: {userdata.order.get_summary()}\n")

    # Create session with userdata
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-matthew",
            style="Conversation",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,  # Pass userdata to session
    )

    # Metrics collection
    usage_collector = metrics.UsageCollector()
    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent):
        usage_collector.collect(ev.metrics)

    await session.start(
        agent=BaristaAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        ),
    )

    await ctx.connect()

# ======================================================
# ⚡ APPLICATION BOOTSTRAP & LAUNCH
# ======================================================
if __name__ == "__main__":
    print("\n" + "⚡" * 25)
    print("🎬 STARTING COFFEE SHOP AGENT...")
    print("⚡" * 25 + "\n")
    
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
