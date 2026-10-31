CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,name TEXT,role TEXT,salt TEXT,hash TEXT);

CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INT,expires REAL);

CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY,name TEXT,price INT,cycle TEXT,tax INT,min_qty INT DEFAULT 1);

CREATE TABLE IF NOT EXISTS subscriptions(id INTEGER PRIMARY KEY,customer TEXT,email TEXT,plan_id INT,qty INT,state TEXT,due TEXT,discount INT DEFAULT 0,discount_end TEXT,discount_limit INT DEFAULT 0,discount_used INT DEFAULT 0);

CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,subscription_id INT,period TEXT,customer TEXT,email TEXT,subtotal INT,discount INT,tax INT,total INT,state TEXT DEFAULT 'Confirmed',UNIQUE(subscription_id,period));

CREATE TABLE IF NOT EXISTS bank(id INTEGER PRIMARY KEY,fingerprint TEXT UNIQUE,reference TEXT,customer TEXT,amount INT,date TEXT,method TEXT);

CREATE TABLE IF NOT EXISTS allocations(id INTEGER PRIMARY KEY,bank_id INT,invoice_id INT,amount INT CHECK(amount>0),FOREIGN KEY(bank_id) REFERENCES bank(id),FOREIGN KEY(invoice_id) REFERENCES invoices(id));

CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT DEFAULT CURRENT_TIMESTAMP,event TEXT);

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);

CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY,invoice_id INT,at TEXT DEFAULT CURRENT_TIMESTAMP,status TEXT);
