import sys
import time
import asyncio
import traceback

from discord.ext import commands

RYRY_ID = 202995638860906496
ABELIAN_ID = 414873201349361664  # Ryry alt
MARIO_RYAN_ID = 528770932613971988  # Ryry alt
UNITARITY_ID = 528770932613971988  # Ryry alt

RYRY_RAI_BOT_ID = 270366726737231884
RAI_TEST_BOT_ID = 536170400871219222

class HeartbeatMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    async def cog_check(self, ctx):
        if self.bot.user.id in [RYRY_RAI_BOT_ID, RAI_TEST_BOT_ID]:  # If it's Ryry's Rai bot
            return ctx.author.id in [RYRY_ID, ABELIAN_ID, MARIO_RYAN_ID, UNITARITY_ID]
        else:
            return ctx.author.id == self.bot.owner_id

    async def subdivision_sleep(self, time_in, period):
        """Sleeps for a given time, subdivided into smaller periods."""
        for _ in range(int(time_in / period)):
            await asyncio.sleep(period)
            
    @commands.command()
    async def heartbeat(self, ctx):
        """Toggle the heartbeat monitor."""
        # all confirmation of starts and stops of heartbeat monitor are taken care of in the f1 function
        if hasattr(self.bot, 'heartbeat_monitor'):
            if self.bot.heartbeat_monitor:
                self.bot.heartbeat_monitor = False
            else:
                # invoke f1 with 0.1 period
                await self.f1(ctx, 0.1)
        else:
            # invoke f1 with 0.1 period
            await self.f1(ctx, 0.1)
            
            
    @commands.command()
    async def f1(self, ctx, period=0.1):
        """
        Starts the heartbeat monitor and continuously checks for interruptions.
        """
        t1 = time.perf_counter()
        for _ in range(50):
            await asyncio.sleep(0.0000001)
        t2 = time.perf_counter()
        sleep_time = (t2 - t1) / 50
        period -= sleep_time
        assert period > 0, f"Period is {period}"
        
        self.bot.heartbeat_monitor = True
        
        await ctx.send(
            f"Heartbeat monitor started with a period of {period:.3f} seconds. Use `;heartbeat` to stop."
        )
        
        while self.bot.heartbeat_monitor:
            iteration_start = time.perf_counter()
            await asyncio.sleep(period)
            iteration_end = time.perf_counter()
            
            iteration_duration = iteration_end - iteration_start
            excess = iteration_duration - period
            
            # Detect interruptions
            if iteration_duration > period * 1.2:  # Allow a 20% buffer before flagging an issue
                await ctx.send(
                    f"Heartbeat interruption detected! Iteration time: {iteration_duration:.4f} seconds "
                    f"(excess ~{excess:.3f}s)"
                )
                # Capture stack trace of all threads
                # noinspection PyProtectedMember, PyUnresolvedReferences
                frames = sys._current_frames()
                for thread_id, frame in frames.items():
                    print(f"\n\nThread {thread_id}:")
                    for line in traceback.format_stack(frame):
                        print(line.strip())
                        
        await ctx.send("Heartbeat monitor stopped.")
    
    @commands.command()
    async def f2(self, ctx):
        t1 = time.perf_counter()
        await asyncio.sleep(4)
        t_block = time.perf_counter()
        time.sleep(2)
        t_unblock = time.perf_counter()
        await asyncio.sleep(4)
        t2 = time.perf_counter()
        await ctx.send(
            f"Function 2 completed in {t2 - t1:.2f} seconds\n"
            f"Blocking sleep duration: {t_unblock - t_block:.2f} seconds"
        )
        
    @commands.command()
    async def f3(self, ctx, sleep_time = 2):
        time.sleep(sleep_time)
        
    @commands.command()
    async def f4(self, ctx):
        await asyncio.sleep(15)
        
    @commands.command()
    async def task_hook(self, ctx):
        def task_creation_hook(_loop, context):
            print("Task added to the event loop!")
            if "task" in context:
                task = context["task"]
                print(f"Task: {task}")
                print(f"Created at: {''.join(task.get_stack(limit=10))}")
            elif "future" in context:
                future = context["future"]
                print(f"Future: {future}")
        
        # Enable the hook
        loop = asyncio.get_event_loop()
        loop.set_task_factory(task_creation_hook)
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        if not hasattr(self.bot, 'command_times'):
            self.bot.command_times = {}
        
        cmd_str = str((ctx.command.qualified_name, ctx.author.id, ctx.message.created_at.timestamp()))
        if cmd_str not in self.bot.command_times:
            self.bot.command_times[cmd_str] = discord.utils.utcnow().timestamp()
    
    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        """Check timing for commands"""
        if not hasattr(self.bot, 'command_times'):
            self.bot.command_times = {}
        
        cmd_str = str((ctx.command.qualified_name, ctx.author.id, ctx.message.created_at.timestamp()))
        if cmd_str not in self.bot.command_times:
            return
        
        elapsed_time = discord.utils.utcnow().timestamp() - self.bot.command_times[cmd_str]
        del self.bot.command_times[cmd_str]
        if elapsed_time > 1:
            print(f"Command {ctx.command.qualified_name} took {elapsed_time} seconds.")
        
        if not hasattr(self.bot, "event_times"):
            self.bot.event_times = defaultdict(list)
        latency = round(self.bot.live_latency, 4)  # time in seconds, for example, 0.08629303518682718
        command_name = ctx.command.qualified_name
        
        self.bot.event_times[command_name].append((int(discord.utils.utcnow().timestamp()),
                                                   latency,
                                                   round(elapsed_time, 4)))


async def setup(bot):
    await bot.add_cog(HeartbeatMonitor(bot))
    