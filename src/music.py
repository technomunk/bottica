# Music-playing Cog for the bot

import logging
import random
import traceback
from collections import deque
from os import path
from typing import Sequence

import discord
from discord.ext import commands
from youtube_dl import YoutubeDL

import response

DATA_FOLDER = 'data/'
CACHE_FOLDER = DATA_FOLDER + 'cache/'

logger = logging.getLogger(__name__)


async def check_author_is_voice_connected(ctx: commands.Context) -> bool:
	if ctx.author.voice is None:
		return False
	
	if ctx.voice_client is None:
		await ctx.author.voice.channel.connect()
	else:
		await ctx.voice_client.move_to(ctx.author.voice.channel)
	return True


def check_author_is_dj(ctx: commands.Context) -> bool:
	return '@dj' in ctx.author.roles


class MusicCog(commands.Cog, name='Music'):
	def __init__(self, bot: commands.Bot) -> None:
		self.bot = bot
		ytdl_options = {
			'format': 'bestaudio',
			'outtmpl': CACHE_FOLDER + '%(title)s-%(id)s.%(ext)s',
			'cachedir': DATA_FOLDER + 'dlcache',
			'download_archive': DATA_FOLDER + 'dlarchive.txt',
			'ignoreerrors': True,
			'quiet': True,
		}
		self.ytdl = YoutubeDL(ytdl_options)
		self.queue = deque()
		self.voice_client = None
		self.is_shuffling = False
		logger.debug('MusicCog initialized')


	async def _queue_audio(self, infos: Sequence[dict]):
		logger.debug('queueing audio')
		if self.is_shuffling:
			# pick a random url and process it first, keeping the rest in order
			idx = random.randrange(1, len(infos))
			infos[0], infos[idx] = infos[idx], infos[0]

		for info in infos:
			filename = self.ytdl.prepare_filename(info)
			if path.exists(filename):
				logger.debug('found %s', filename)
				self.queue.append(filename)
			else:
				url = info['url']
				logger.debug('downloading %s', url)
				# download should be run asynchronously as to avoid blocking the bot
				info = await self.bot.loop.run_in_executor(None, lambda: self.ytdl.extract_info(url))
				if not info:
					logger.warn('skipping %s because it could not be downloaded!', url)
					continue
				self.queue.append(filename)
			if not self.is_playing():
				self.play_next()


	def is_playing(self):
		return self.voice_client is not None and self.voice_client.is_playing()


	@commands.command(aliases=('p',))
	@commands.check(check_author_is_voice_connected)
	async def play(self, ctx: commands.Context, query: str):
		'''
		Play provided input.
		'''
		self.voice_client = ctx.voice_client
		# download should be run asynchronously as to avoid blocking the bot
		info = await self.bot.loop.run_in_executor(
			None,
			lambda: self.ytdl.extract_info(query, download=False),
		)
		if info:
			await ctx.reply(random.choice(response.SUCCESSES))
		else:
			return await ctx.reply(random.choice(response.FAILS))

		if 'entries' in info:
			await self._queue_audio([entry for entry in info['entries']])
		else:
			await self._queue_audio((info,))
		# actual playing will happen once audio is available
	

	@commands.command()
	async def shuffle(self, ctx: commands.context):
		'''
		Toggle shuffling of the queued playlist.
		'''
		self.is_shuffling = not self.is_shuffling
		if self.is_shuffling:
			resp = 'Shuffling queued songs.'
		else:
			resp = 'Playing queued songs in order.'
		await ctx.reply(resp)
	

	@commands.command()
	async def next(self, ctx: commands.Context):
		'''
		Skip the current song.
		'''
		if not self.is_playing():
			return await ctx.reply("I'm not playing anything." + random.choice(response.FAILS))
		
		self.play_next(pause=True)
		await ctx.reply(random.choice(response.SUCCESSES))
	

	def play_next(self, pause=False):
		'''
		Play the next song in the queue.
		'''
		if self.voice_client is None or self.voice_client.channel is None:
			raise RuntimeError("Bot is not connected to voice to play.")
		
		if not self.queue:
			logger.debug('empty queue')
			if pause and self.is_playing():
				self.voice_client.stop()
			return
		
		if not self.voice_client.is_connected():
			return logger.warn('Client is not connected!')
		
		if self.is_shuffling:
			idx = random.randrange(len(self.queue))
			file = self.queue[idx]
			del self.queue[idx]
		else:
			file = self.queue.popleft()
		
		if not file:
			return logger.warn('Attempted to play an empty file!')
		
		if self.is_playing():
			self.voice_client.pause()
		
		def handle_after(error):
			if error is None:
				self.play_next()
			else:
				logger.error('encountered error: %s', error)
		
		self.voice_client.play(discord.FFmpegPCMAudio(file, options='-vn'), after=handle_after)
		logger.debug('playing %s', file)
