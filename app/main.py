import asyncio
import aiohttp
import json
import os

CONFIG_PATH = "/app/config.json"
DATA_DIR = "/data"
DUMP_DIR = f"{DATA_DIR}/dump"
PROGRESS_FILE = f"{DATA_DIR}/progress.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


async def tg_log(session, text, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        await session.post(url, json={"chat_id": chat_id, "text": text})
    except:
        pass


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"last_offset": 0, "total_saved": 0, "file_index": 0}


def save_progress(offset, total_saved, file_index):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(
            {"last_offset": offset, "total_saved": total_saved, "file_index": file_index},
            f,
            indent=2
        )


async def fetch_batch(session, offset, batch, api_key):
    url = (
        f"https://apilist.tronscan.org/api/account/list"
        f"?sort=-balance&limit={batch}&start={offset}"
    )
    async with session.get(url, headers={"TRON-PRO-API-KEY": api_key}) as resp:
        return (await resp.json()).get("data", [])


async def main():
    cfg = load_config()

    api_key = cfg["API_KEY"]
    tg_token = cfg["TG_TOKEN"]
    tg_chat = cfg["TG_CHAT_ID"]
    batch = cfg["BATCH_SIZE"]
    delay = cfg["DELAY"]

    os.makedirs(DUMP_DIR, exist_ok=True)

    progress = load_progress()
    offset = progress["last_offset"]
    total_saved = progress["total_saved"]
    file_index = progress["file_index"]

    current_file_path = f"{DUMP_DIR}/addresses_{file_index}.jsonl"
    current_file = open(current_file_path, "a")

    async with aiohttp.ClientSession() as session:
        await tg_log(session, f"🚀 Collector started from offset={offset}", tg_token, tg_chat)

        while True:
            try:
                batch_data = await fetch_batch(session, offset, batch, api_key)

                if not batch_data:
                    await tg_log(session, f"🛑 Empty batch at offset={offset}. End.", tg_token, tg_chat)
                    break

                for row in batch_data:
                    current_file.write(json.dumps(row, ensure_ascii=False) + "\n")

                total_saved += len(batch_data)
                offset += batch

                # ротация файла каждые 100к
                if total_saved % 100000 == 0:
                    current_file.close()
                    file_index += 1
                    current_file = open(f"{DUMP_DIR}/addresses_{file_index}.jsonl", "a")

                save_progress(offset, total_saved, file_index)

                print(f"Saved: {total_saved} | offset={offset}")
                await tg_log(
                    session,
                    f"✔ Batch OK. Total={total_saved}, offset={offset}",
                    tg_token,
                    tg_chat
                )

            except Exception as e:
                await tg_log(
                    session,
                    f"❌ Error: {e}. Offset={offset}",
                    tg_token,
                    tg_chat
                )
                save_progress(offset, total_saved, file_index)
                await asyncio.sleep(3)
                continue

            await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(main())
