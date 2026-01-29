import asyncio
import logging

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self):
        self.queue = asyncio.Queue()

    async def add_task(self, command: str):
        """Add a command to the queue"""
        await self.queue.put(command)
        logger.info(f"Task added: {command}")

    async def get_next_task(self):
        """Get next task"""
        return await self.queue.get()

    def task_done(self):
        self.queue.task_done()

# Singleton instance
queue = TaskQueue()
