from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from claw_wechat_parser.config import load_settings
from claw_wechat_parser.domain.message import InboundMessage
from claw_wechat_parser.logging import setup_logging
from claw_wechat_parser.services.parse_service import ParseService
from claw_wechat_parser.storage.accounts import AccountStore
from claw_wechat_parser.weixin.auth import WeixinAuthService
from claw_wechat_parser.weixin.poller import WeixinPoller

app = typer.Typer(help="微信 Claw/iLink 链接解析 Bot")
accounts_app = typer.Typer(help="账号管理")
app.add_typer(accounts_app, name="accounts")
console = Console()

StateOpt = Annotated[Path | None, typer.Option("--state-dir", help="状态目录，默认 ~/.claw-wechat-parser")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="输出调试日志")]


@app.command("login-wechat")
def login_wechat(state_dir: StateOpt = None, verbose: VerboseOpt = False) -> None:
    """启动微信扫码登录，并将 token 保存到本地状态目录。"""
    setup_logging(verbose)
    settings = load_settings(state_dir)
    store = AccountStore(settings.accounts_dir)

    async def runner() -> None:
        result = await WeixinAuthService(settings).login_with_qr(verbose=verbose)
        if not result.connected or not result.account:
            console.print(f"[red]登录失败：{result.message}[/red]")
            raise typer.Exit(1)
        path = store.save(result.account)
        console.print(f"[green]✅ {result.message}[/green]")
        console.print(f"账号：{result.account.account_id}")
        console.print(f"已保存：{path}")

    asyncio.run(runner())


@app.command("serve")
def serve(
    account_id: Annotated[str | None, typer.Option("--account", "-a", help="账号 ID；为空时使用第一个已登录账号")] = None,
    state_dir: StateOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """启动微信长轮询服务，收到链接后自动解析并回复。"""
    setup_logging(verbose)
    settings = load_settings(state_dir)
    store = AccountStore(settings.accounts_dir)
    accounts = store.list()
    if account_id:
        account = store.load(account_id)
        if not account:
            raise typer.BadParameter(f"账号不存在：{account_id}")
    else:
        if not accounts:
            raise typer.BadParameter("没有已登录账号，请先运行 claw-parser login-wechat")
        account = accounts[0]

    async def runner() -> None:
        poller = WeixinPoller(settings, account)
        try:
            await poller.run_forever()
        finally:
            await poller.close()

    console.print(f"启动账号：[cyan]{account.account_id}[/cyan]")
    asyncio.run(runner())


@app.command("parse")
def parse_text(
    text: Annotated[str, typer.Argument(help="要测试解析的文本/链接")],
    state_dir: StateOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """本地测试解析器，不连接微信。"""
    setup_logging(verbose)
    settings = load_settings(state_dir)

    async def runner() -> None:
        service = ParseService(settings)
        try:
            inbound = InboundMessage(
                account_id="local",
                from_user_id="local-user",
                to_user_id="local-bot",
                text=text,
                message_id="local-test",
            )
            outbound = await service.parse_message(inbound)
            if not outbound:
                console.print("[yellow]未匹配到解析器[/yellow]")
                return
            console.print(outbound.text)
            for media in outbound.media:
                console.print(f"MEDIA {media.kind}: {media.path}")
        finally:
            await service.close()

    asyncio.run(runner())


@accounts_app.command("list")
def accounts_list(state_dir: StateOpt = None, verbose: VerboseOpt = False) -> None:
    """列出本地已登录微信账号。"""
    setup_logging(verbose)
    settings = load_settings(state_dir)
    accounts = AccountStore(settings.accounts_dir).list()
    table = Table(title="WeChat Accounts")
    table.add_column("account_id")
    table.add_column("user_id")
    table.add_column("base_url")
    table.add_column("enabled")
    for account in accounts:
        table.add_row(account.account_id, account.user_id or "", account.base_url, str(account.enabled))
    console.print(table)


@accounts_app.command("remove")
def accounts_remove(
    account_id: Annotated[str, typer.Argument(help="账号 ID")],
    state_dir: StateOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """删除本地账号凭据。"""
    setup_logging(verbose)
    settings = load_settings(state_dir)
    ok = AccountStore(settings.accounts_dir).remove(account_id)
    console.print("已删除" if ok else "账号不存在")
