# Discord bot entry point.
# Register and run the main logic.

import random
from argparse import ArgumentParser

import discord
from discord.ext.commands import Bot as DiscordBot
from discord.mentions import AllowedMentions
from discord_slash import SlashCommand, SlashContext

from music import MusicCog

BOT_VERSION = '1.1.0'

bot = DiscordBot(
	'.',
	intents=discord.Intents.default(),
	allowed_mentions=AllowedMentions(users=True),
)
slash = SlashCommand(bot)

@bot.event
async def on_ready():
	print(f'Logged in as {bot.user.name}.')
	print(f'User id: {bot.user.id}')
	print('Guilds:')
	for guild in bot.guilds:
		print(f'{guild.name} (id: {guild.id})')


@slash.slash()
async def version(ctx: SlashContext):
	'''
	Print the current bot version.
	'''
	await ctx.send(f"My version is `{BOT_VERSION}`.")


@slash.slash()
async def rate(ctx: SlashContext, user: discord.Member):
	'''
	Rate the provided user out of 10.
	'''
	print(f'Rating {user.display_name} (id: {user.id})')
	if user.id == 305440304528359424 or user == bot.user:
		rating = 10
	else:
		rating = random.randint(1, 9)
	await ctx.send(f'{user.mention} is {rating}/10.')


def run_bot():
	parser = ArgumentParser(prog='bottica', description='Run a discord bot named "Bottica".')
	parser.add_argument('--sync', action='store_true', help='Synchronize bot commands with discord.')
	parser.add_argument('--debug-guild', type=int, help='Debug Guild id to use.')

	args = parser.parse_args()

	token = ''
	try:
		with open('.token') as token_file:
			token = token_file.readline()
	except FileNotFoundError:
		print('Please create a ".token" file with a bot token to use.')
		return
	
	if args.sync:
		print("Synchronizing commands")
		bot.loop.create_task(slash.sync_all_commands())
	
	slash.debug_guild = args.debug_guild
	
	bot.add_cog(MusicCog(bot))
	bot.run(token)


if __name__ == '__main__':
	run_bot()
