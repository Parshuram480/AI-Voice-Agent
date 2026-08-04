-- ==========================================================
-- OUTREACH DUMMY DATA SCRIPT (ORIGINAL JSON DATA)
-- ==========================================================

-- ==========================================================
-- 1. B2B SALES (products)
-- ==========================================================
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    price TEXT,
    in_stock BOOLEAN,
    rating REAL,
    description TEXT,
    discount TEXT
);

INSERT INTO products (id, name, category, price, in_stock, rating, description, discount) VALUES
('WIFI-100', 'Nova Basic 100Mbps', 'Internet Plans', '$39.99/month', 1, 4.2, 'Reliable 100Mbps Wi-Fi plan perfect for light browsing, social media, and SD streaming on 1-2 devices.', NULL),
('WIFI-500', 'Nova Stream 500Mbps', 'Internet Plans', '$59.99/month', 1, 4.7, 'Fast 500Mbps plan ideal for families, HD streaming on multiple devices, and smooth video calls.', 'First month free'),
('WIFI-1G', 'Nova Gamer Pro 1Gbps Fiber', 'Internet Plans', '$89.99/month', 1, 4.9, 'Ultra-fast 1 Gigabit Fiber internet. Essential for hardcore gamers, 4K streaming, and heavy smart home usage with ultra-low latency.', 'Includes free router upgrade'),
('HW-ROUTER-MESH', 'Nova Whole-Home Mesh System', 'Hardware Add-ons', '$9.99/month or $120 upfront', 1, 4.8, 'Eliminate dead zones with our powerful 3-pack mesh Wi-Fi system. Perfect for large houses over 2000 sq ft.', NULL),
('HW-EXTENDER', 'Nova Range Extender', 'Hardware Add-ons', '$4.99/month or $40 upfront', 0, 3.9, 'Simple plug-in Wi-Fi extender for a single room.', NULL);


-- ==========================================================
-- 2. REAL ESTATE (properties)
-- ==========================================================
CREATE TABLE IF NOT EXISTS properties (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    price TEXT,
    status TEXT,
    bedrooms INTEGER,
    bathrooms REAL,
    sqft INTEGER,
    year_built INTEGER,
    address TEXT,
    neighborhood TEXT,
    description TEXT,
    hoa_fee TEXT,
    property_tax TEXT,
    rating REAL,
    discount TEXT
);

INSERT INTO properties (id, name, category, price, status, bedrooms, bathrooms, sqft, year_built, address, neighborhood, description, hoa_fee, property_tax, rating, discount) VALUES
('PROP-APT-01', 'The Metro Lofts - Unit 4B', 'Apartments', '$215,000', 'available', 1, 1, 750, 2015, '400 Downtown Ave, City Center', 'City Center', 'Modern 1-bedroom loft in the heart of downtown. Features exposed brick, high ceilings, and stainless steel appliances.', '$250/month', '$2,100/year', 4.5, NULL),
('PROP-APT-02', 'Riverview Condos - Unit 12C', 'Apartments', '$310,000', 'available', 2, 2, 1100, 2020, '1200 Riverside Dr, Riverfront', 'Riverfront', 'Stunning 2-bedroom corner unit with panoramic river views and a private balcony.', '$320/month', '$3,200/year', 4.7, 'Seller offering to cover first 6 months of HOA fees'),
('PROP-TWN-01', 'Maplewood Terraces', 'Townhomes', '$385,000', 'available', 3, 2.5, 1650, 2018, '45 Maplewood Ln, Maplewood', 'Maplewood', 'Spacious 3-story townhome with a small private yard and attached 2-car garage. Perfect for a growing family.', '$150/month', '$4,100/year', 4.6, NULL),
('PROP-SFH-01', 'The Greenwood Classic', 'Single-Family Homes', '$475,000', 'available', 4, 2.5, 2200, 2012, '742 Greenwood Dr, Greenwood Heights', 'Greenwood Heights', 'Beautiful 4-bedroom family home in highly sought-after Greenwood Heights. Features an open-plan kitchen and a large fenced backyard.', '$0/month', '$5,200/year', 4.8, NULL),
('PROP-SFH-02', 'Sunnyvale Ranch', 'Single-Family Homes', '$525,000', 'pending', 3, 2, 1950, 1998, '88 Sunnyvale Rd, Westside', 'Westside', 'Charming single-story ranch home with a recently renovated kitchen and massive backyard.', '$0/month', '$4,800/year', 4.4, NULL),
('PROP-LUX-01', 'The Summit Estate', 'Luxury Estates', '$1,150,000', 'available', 5, 4.5, 4500, 2023, '100 Summit Ridge, The Palisades', 'The Palisades', 'Magnificent luxury estate featuring a chef''s kitchen, home theater, infinity pool, and spectacular valley views.', '$400/month', '$12,500/year', 4.9, 'Price recently reduced by $50k');

