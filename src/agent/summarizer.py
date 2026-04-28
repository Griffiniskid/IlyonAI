"""Background summarizer: fires every 10 assistant turns, stores transcript summary in Greenfield."""
from sqlalchemy import select, func
from src.storage.greenfield import GreenfieldClient
from src.config import settings


async def maybe_summarize(db, *, router, chat_id, user_id):
    """Check turn count and summarize if at a 10-turn boundary."""
    from src.models.chat import ChatMessage
    greenfield = GreenfieldClient()

    count_r = await db.execute(
        select(func.count(ChatMessage.id))
        .where(ChatMessage.chat_id == chat_id, ChatMessage.role == "assistant"))
    count = count_r.scalar_one()
    if count == 0 or count % 10 != 0:
        return

    msgs_r = await db.execute(
        select(ChatMessage).where(ChatMessage.chat_id == chat_id)
                            .order_by(ChatMessage.created_at))
    transcript = "\n".join(f"{m.role}: {m.content}" for m in msgs_r.scalars())

    summary = await router.complete(
        model="default",
        messages=[{"role": "system", "content": "Summarize this chat as context for future turns, <= 400 tokens."},
                  {"role": "user", "content": transcript}],
        temperature=0.2, stop=None,
    )

    await greenfield.put_object(
        key=f"{user_id}/{chat_id}.json",
        body=summary["content"].encode(),
    )
