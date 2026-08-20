"""
向量库全量重建脚本

用法：
    cd backend
    python import_data/rebuild_vectorstore.py

说明：
    - 默认断点续传（resume=True），上次失败可从中断处继续
    - 如需从头重建，传入 --from-scratch：
      python import_data/rebuild_vectorstore.py --from-scratch
    - 进度保存在 chroma_db/rebuild_checkpoint.json
"""

import sys
import argparse
import logging
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.services.rag_service import rebuild_vectorstore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="重建 Chroma 向量库")
    parser.add_argument(
        "--from-scratch",
        action="store_true",
        help="从头重建，忽略 checkpoint 并清空已有集合",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rebuild_vectorstore(db, resume=not args.from_scratch)
    except Exception as e:
        logger.error(f"向量库重建失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
