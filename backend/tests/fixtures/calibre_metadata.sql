-- Minimal subset of Calibre's metadata.db schema + fixture data for the sync tests.
-- Only the tables/columns the selection query touches are modelled; loaded into an
-- in-memory connection (see tests/test_calibre.py).
--
-- Coverage of the selection rule (tag = 'Food' AND format IN (...)):
--   100  included — full metadata: isbn, single author, comments, valid pubdate
--   200  included — two authors (GROUP_CONCAT ' & '), no isbn, no comments, NULL pubdate
--   500  included — malformed pubdate (exercises defensive parsing -> NULL)
--   400  PDF only — included when PDF is selected, excluded when EPUB alone is
--   600  both formats — must still yield exactly one row (SELECT DISTINCT)
--   300  excluded — wrong tag ('Fiction')

CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    pubdate TEXT,
    timestamp TEXT
);

CREATE TABLE authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE books_authors_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    author INTEGER NOT NULL
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE books_tags_link (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    tag INTEGER NOT NULL
);

CREATE TABLE data (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    format TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE identifiers (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    type TEXT NOT NULL,
    val TEXT NOT NULL
);

CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    book INTEGER NOT NULL,
    text TEXT NOT NULL
);

INSERT INTO books (id, title, path, pubdate, timestamp) VALUES
    (100, 'Salt, Fat, Acid, Heat', 'Samin Nosrat/Salt, Fat, Acid, Heat (100)', '2017-04-25 00:00:00+00:00', '2020-01-02 10:30:00+00:00'),
    (200, '1,000 Indian Recipes', 'Neelam Batra/1,000 Indian Recipes (200)', NULL, '2021-06-15 08:00:00+00:00'),
    (300, 'The Great Gatsby', 'F Scott Fitzgerald/The Great Gatsby (300)', '1925-04-10 00:00:00+00:00', '2019-01-01 00:00:00+00:00'),
    (400, 'Cookbook (PDF Only)', 'Some Author/Cookbook PDF Only (400)', '2010-01-01 00:00:00+00:00', '2018-01-01 00:00:00+00:00'),
    (500, 'Cooking With Bad Dates', 'A Chef/Cooking With Bad Dates (500)', 'not-a-real-date', '2022-03-03 12:00:00+00:00'),
    (600, 'Cookbook (Both Formats)', 'Some Author/Cookbook Both Formats (600)', '2015-05-05 00:00:00+00:00', '2023-04-04 09:00:00+00:00');

INSERT INTO authors (id, name) VALUES
    (1, 'Samin Nosrat'),
    (2, 'Neelam Batra'),
    (3, 'Jeyashri Suresh'),
    (4, 'F. Scott Fitzgerald'),
    (5, 'Some Author'),
    (6, 'A Chef');

INSERT INTO books_authors_link (id, book, author) VALUES
    (1, 100, 1),
    (2, 200, 2),
    (3, 200, 3),
    (4, 300, 4),
    (5, 400, 5),
    (6, 500, 6),
    (7, 600, 5);

INSERT INTO tags (id, name) VALUES
    (1, 'Food'),
    (2, 'Fiction');

INSERT INTO books_tags_link (id, book, tag) VALUES
    (1, 100, 1),
    (2, 200, 1),
    (3, 300, 2),
    (4, 400, 1),
    (5, 500, 1),
    (6, 600, 1);

INSERT INTO data (id, book, format, name) VALUES
    (1, 100, 'EPUB', 'Salt, Fat, Acid, Heat'),
    (2, 200, 'EPUB', '1,000 Indian Recipes'),
    (3, 300, 'EPUB', 'The Great Gatsby'),
    (4, 400, 'PDF', 'Cookbook PDF Only'),
    (5, 500, 'EPUB', 'Cooking With Bad Dates'),
    (6, 600, 'EPUB', 'Cookbook Both Formats'),
    (7, 600, 'PDF', 'Cookbook Both Formats');

INSERT INTO identifiers (id, book, type, val) VALUES
    (1, 100, 'isbn', '9781476753836'),
    (2, 100, 'google', 'abc123');

INSERT INTO comments (id, book, text) VALUES
    (1, 100, 'Mastering the elements of good cooking.'),
    (2, 300, 'A novel, not a cookbook.');
