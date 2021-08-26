# Discord bot entry point.
# Register and run the main logic.

from argparse import ArgumentParser

import discord
from discord_slash import SlashCommand, SlashContext

BOT_VERSION = '0.1.0'

bot = discord.Client(intents=discord.Intents.default())
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
	
	bot.run(token)


if __name__ == '__main__':
	run_bot()
