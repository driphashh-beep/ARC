"""Optional Discord bridge: no DMs and configured channel only."""
import os
import arc_core as core

def discord_config():
    token, channel = os.getenv("DISCORD_BOT_TOKEN", ""), os.getenv("ARC_DISCORD_CHANNEL_ID", "")
    try: channel_id = int(channel) if channel else 0
    except ValueError: channel_id = 0
    return {"configured": bool(token and channel_id), "channel_id": channel_id}

def allowed_interaction(interaction, channel_id):
    return getattr(interaction, "guild_id", None) is not None and getattr(interaction, "channel_id", None) == channel_id

def run_discord():
    config = discord_config()
    if not config["configured"]: return
    import discord
    from discord import app_commands
    client = discord.Client(intents=discord.Intents.none()); tree = app_commands.CommandTree(client)
    async def guard(interaction):
        if allowed_interaction(interaction, config["channel_id"]): return True
        await interaction.response.send_message("ARC commands are restricted to the configured testing channel.", ephemeral=True); return False
    @tree.command(name="arc", description="Run an ARC testing task")
    async def arc_cmd(interaction: discord.Interaction, task: str):
        if not await guard(interaction): return
        await interaction.response.defer()
        try: result = core.route_chat(task, web_enabled=False)["reply"]
        except Exception as exc: result = f"ARC error: {core.redact(exc)}"
        await interaction.followup.send(core.redact(result)[:1900])
    @tree.command(name="study", description="Create a study guide approval")
    async def study_cmd(interaction: discord.Interaction, text: str, title: str = "Study Guide"):
        if not await guard(interaction): return
        result = core.route_chat(f"Turn this text into a study guide and save it: {title}\n{text}", web_enabled=False)
        result = result["tool_result"]
        message = result.get("error") or f"Created approval #{result['pending_action_id']} for {result['proposed_filename']}. Approve it in the local dashboard."
        await interaction.response.send_message(core.redact(message))
    @tree.command(name="arc_status", description="Show safe ARC status")
    async def status_cmd(interaction: discord.Interaction):
        if not await guard(interaction): return
        summary = core.database_summary()
        await interaction.response.send_message(f"ARC online · Privacy ON · {summary['approvals_pending']} approvals pending · {summary['api_calls_today']}/{core.DAILY_API_CALL_LIMIT} API calls today")
    @client.event
    async def on_ready():
        await tree.sync(); core.log_event("discord_ready", "configured testing channel")
    client.run(os.environ["DISCORD_BOT_TOKEN"], log_handler=None)
