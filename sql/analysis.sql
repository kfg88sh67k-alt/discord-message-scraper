-- Starter analysis queries against output/messages.db.
-- Usage: sqlite3 output/messages.db < sql/analysis.sql

-- Messages per month
SELECT strftime('%Y-%m', created_at) AS month,
       COUNT(*) AS messages
FROM messages
GROUP BY month
ORDER BY month;

-- Top authors
SELECT author_username,
       COUNT(*) AS messages
FROM messages
GROUP BY author_id
ORDER BY messages DESC
LIMIT 20;

-- Activity by hour of day (UTC)
SELECT strftime('%H', created_at) AS hour,
       COUNT(*) AS messages
FROM messages
GROUP BY hour
ORDER BY hour;

-- Replies vs total per author
SELECT author_username,
       SUM(CASE WHEN reply_to_id IS NOT NULL THEN 1 ELSE 0 END) AS replies,
       COUNT(*) AS total
FROM messages
GROUP BY author_id
ORDER BY replies DESC
LIMIT 20;

-- Most-replied-to messages
SELECT m.id,
       m.author_username,
       m.content,
       COUNT(r.id) AS reply_count
FROM messages m
JOIN messages r ON r.reply_to_id = m.id
GROUP BY m.id
ORDER BY reply_count DESC
LIMIT 20;
