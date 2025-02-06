import sys
import time
import asyncio
import traceback
from collections import defaultdict
from functools import wraps
from typing import Generator, Any

import discord.utils
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
            return ctx.author.id == self.bot.owner_id  # only owner can use these commands

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
            if iteration_duration > period * 5:  # Allow a 50% buffer before flagging an issue
                print(
                    f"Heartbeat interruption detected! Iteration time: {iteration_duration:.4f} seconds "
                    f"(excess ~{excess:.3f}s)"
                )
                
                if not hasattr(self.bot, "tasks_at_high_heartbeat"):
                    self.bot.tasks_at_high_heartbeat = []
                self.bot.tasks_at_high_heartbeat.append(await self.tasks_internal(ctx, show_prints=False))
                
                # Capture stack trace of all threads
                # noinspection PyProtectedMember, PyUnresolvedReferences
                # frames = sys._current_frames()
                # for thread_id, frame in frames.items():
                #     print(f"\n\nThread {thread_id}:")
                #     for line in traceback.format_stack(frame):
                #         print(line.strip())
                        
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
    
    @staticmethod
    def end(bot: commands.Bot, loop, t_in, cog):
        def end_inner(task):
            t_now = loop.time()
            diff = t_now - t_in
            
            latency = round(bot.live_latency, 4)  # time in seconds, for example, 0.08629303518682718
            
            # get task name
            task_name = task.get_name()
            coro_name = f"({getattr(task.get_coro(), '__qualname__', str(task.get_coro()))}) "
            
            if "on_message" in task_name or "Message" in coro_name:
                return  # basic timer will take care of this, otherwise this will include command call times
            if task_name.startswith("discord.py: "):  # event names like "discord.py: on_message"
                task_name = task_name.replace("discord.py: ", "")
            elif task_name.startswith("Task-"):  # uses generic task name, use coro name instead
                task_name = coro_name
            if task_name == 'delete':
                return  # this is for things like send(...delete_after=5), will always record "5s" as the time
            
            # subtract known wait times from commands that did wait_for()
            if hasattr(bot, "wait_for_times"):
                if task_name.startswith("on_"):
                    task_name = task_name[3:]
                if task_name in bot.wait_for_times:
                    diff -= bot.wait_for_times[task_name].pop(0)
                    del bot.wait_for_times[task_name]
            
            if diff < 1:
                return
            
            # add cog to name
            if cog:
                task_name = f"{cog}.{task_name}"
               
            if not hasattr(bot, "event_times"):
                bot.event_times = defaultdict(list)
            bot.event_times[task_name].append((int(discord.utils.utcnow().timestamp()),
                                                              latency,
                                                              round(diff, 4)))
            
            if "_run_event" in coro_name:
                coro_name = ""
            s = f"ENDING Task {task_name} {coro_name}has ended in {diff:.4f}s (latency: {bot.live_latency:.4f}s)."
            coro = task.get_coro()
            if getattr(coro, "cr_origin", None):
                for line_tuple in task.get_coro().cr_origin:
                    if "Rai" in line_tuple[0]:
                        s += f"\n  {line_tuple[0].strip()} ({line_tuple[2]} line {line_tuple[1]})"
            try:
                message_content = coro.cr_frame.f_locals["args"][0].content
                s += f"\n  Message content: {message_content}"
            except (AttributeError, KeyError):
                pass
            print(s)
        return end_inner

    @staticmethod
    def end2(task):
        print(f"Task {task.get_name()} ({task.get_coro().__name__}) has ended.")

    @commands.command()
    async def task_hook(self, ctx):
        def task_creation_hook(_loop: asyncio.AbstractEventLoop,
                               _coro: Generator[Any, None, Any]):
            """factory must be a callable with the signature matching (loop, coro, context=None),
            where loop is a reference to the active event loop, and coro is a coroutine object.
            The callable must return a asyncio.Future-compatible object."""

            t_now = loop.time()
            task = asyncio.Task(_coro, loop=_loop)
            is_running = getattr(_coro, "cr_running", False)
            try:
                cog = _coro.cr_frame.f_locals['coro'].__self__.qualified_name
            except (KeyError, AttributeError):
                cog = ""
            task.add_done_callback(self.end(self.bot, loop, t_now, cog))
            # task.print_stack()
            # task.add_done_callback(self.end2)
            # print(f"STARTING new task: {task.get_name()} ({_coro.__name__})")
            # co_names = getattr(_coro.cr_code, "co_names", None)
            # if co_names:
            #     print(f"  co_names: {co_names}")
            # co_varnames = getattr(_coro.cr_code, "co_varnames", None)
            # if co_varnames:
            #     print(f"  co_varnames: {co_varnames}")
            # try:
            #     message_content = _coro.cr_frame.f_locals["args"][0].content
            #     print(f"  Message content: {message_content}")
            # except (AttributeError, KeyError):
            #     pass
            # if _coro.cr_origin:
            #     for line_tuple in _coro.cr_origin:
            #         if "Rai" in line_tuple[0]:
            #             print(f"  {line_tuple[0].strip()} ({line_tuple[2]} line {line_tuple[1]})")
            #
            # print()
            return task

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
        
    @commands.command()
    async def tasks(self, ctx):
        await self.tasks_internal(ctx)
        
    async def tasks_internal(self, ctx, show_prints=True):
        # f_locals are stored at task._coro.cr_frame.f_locals
        # on_message f_locals: 'self': Rai, 'coro': Cog.on_message, 'event_name': 'on_message', 'args': (message,), kwargs: {}
        tasks = asyncio.all_tasks()
        for task in tasks:
            try:
                plain_name = task.get_coro().cr_frame.f_locals['event_name']
                new_name = task.get_coro().cr_frame.f_locals['coro'].__qualname__
                task.set_name(task.get_name().replace(plain_name, new_name))
            except (KeyError, AttributeError):
                continue
        background_tasks = [task for task in tasks if task.get_name().startswith("discord-ext-tasks")]
        on_message_tasks = [task for task in tasks if "on_message" in task.get_name()]
        other_tasks = [task for task in tasks if task not in background_tasks and task not in on_message_tasks]
        for task in other_tasks + on_message_tasks:
            if task.get_name() == "Task-1":
                continue
            coro_name = task.get_coro().__qualname__ if task.get_coro() else "N/A"
            if coro_name in ["Client._run_event", "Loop._loop"]:
                coro_name = ""
            state = "done" if task.done() else "pending"
            cancelled = "cancelled" if task.cancelled() else "active"
            result = None
            exception = None
            
            try:
                if task.done():
                    result = task.result()
            except asyncio.CancelledError:
                result = "Cancelled"
            except Exception as e:
                exception = str(e)
            
            # Get source traceback info (if available)
            source = getattr(task, "_source_traceback", None)
            if source:
                source_file = next(iter(source)).filename
                source_line = next(iter(source)).lineno
            else:
                source_file, source_line = "Unknown", "Unknown"
            
            if show_prints:
                print(f"Task: {task.get_name()}")
                print(f"  Coroutine: {coro_name}") if coro_name else None
                print(f"  State: {state} ({cancelled})")
                if result:
                    print(f"  Result: {result}")
                if exception:
                    print(f"  Exception: {exception}")
                print(f"  Created At: {source_file}:{source_line}")
                print("-" * 40)
                
        return [task.get_name() for task in other_tasks + on_message_tasks]

async def setup(bot):
    await bot.add_cog(HeartbeatMonitor(bot))
    