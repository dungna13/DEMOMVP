import asyncio
import logging
from .task_queue import queue

logger = logging.getLogger(__name__)

class Engine:
    def __init__(self):
        self.running = False

    async def start(self):
        logger.info("Engine Started. Waiting for tasks...")
        self.running = True
        
        while self.running:
            # Wait for task
            command = await queue.get_next_task()
            
            # Process task
            logger.info(f"Processing command: {command}")
            await self.execute(command)
            
            queue.task_done()

    async def execute(self, command):
        """Execute the command logic"""
        # Simulation of work
        await asyncio.sleep(2)
        logger.info(f"Command '{command}' completed.")

    def stop(self):
        self.running = False

engine = Engine()
