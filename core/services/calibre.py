import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from core.models import Book

logger = logging.getLogger(__name__)


def load_books_from_calibre(calibre_path: Path):
    db_path = calibre_path / 'metadata.db'

    if not db_path.exists():
        raise FileNotFoundError(f'Calibre database not found at {db_path}')

    logger.info(f'Connecting to Calibre database at {db_path}')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT 
            b.id,
            b.title,
            b.path,
            b.pubdate,
            (SELECT val FROM identifiers WHERE book = b.id AND type = 'isbn' LIMIT 1) as isbn,
            (SELECT name FROM data WHERE book = b.id AND format = 'EPUB' LIMIT 1) as epub_name,
            (SELECT GROUP_CONCAT(a.name, ' & ') 
             FROM authors a 
             JOIN books_authors_link bal ON a.id = bal.author 
             WHERE bal.book = b.id) as authors,
            (SELECT text FROM comments WHERE book = b.id) as description
        FROM books b
        JOIN books_tags_link btl ON b.id = btl.book
        JOIN tags t ON btl.tag = t.id
        JOIN data d ON b.id = d.book
        WHERE t.name = 'Food'
        AND d.format = 'EPUB'
        ORDER BY b.title
    """)

    books_data = cursor.fetchall()
    logger.info(f'Found {len(books_data)} books with "Food" tag and EPUB format')

    created_count = 0
    updated_count = 0

    for row in books_data:
        calibre_id = row['id']
        title = row['title']
        author = row['authors'] or ''
        path = row['path']
        pubdate_str = row['pubdate']
        isbn = row['isbn'] or ''
        description = row['description'] or ''

        pubdate = None
        if pubdate_str:
            try:
                pubdate = datetime.strptime(pubdate_str.split()[0], '%Y-%m-%d').date()
            except (ValueError, IndexError):
                logger.warning(f'Could not parse pubdate for book {calibre_id}: {pubdate_str}')

        _, created = Book.objects.update_or_create(
            calibre_id=calibre_id,
            defaults={
                'title': title,
                'author': author,
                'pubdate': pubdate,
                'isbn': isbn,
                'description': description,
                'path': str(calibre_path / path),
            }
        )

        if created:
            created_count += 1
            logger.info(f'Created: {title}')
        else:
            updated_count += 1
            logger.info(f'Updated: {title}')

    conn.close()
    return created_count, updated_count