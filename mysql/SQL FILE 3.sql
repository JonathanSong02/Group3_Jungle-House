CREATE TABLE wiki_article (
    article_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200),
    content TEXT,
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

#add the table
INSERT INTO wiki_article (title, content, category)
VALUES
('Opening SOP', 'Check stock, clean kiosk, prepare equipment before opening.', 'SOP'),
('Closing SOP', 'Close cash, clean area, store products properly.', 'SOP'),
('Wild Honey Product Information', 'Wild honey has natural benefits and is rich in nutrients.', 'PRODUCT'),
('Customer Approach Sales Tips', 'Greet customer, explain benefits, recommend suitable product.', 'SALES');


#add on new rows
INSERT INTO wiki_article (title, content, category)
VALUES ('Aeon RoadShow Closing', 'Test steps here...', 'SOP');

#delete row 
USE jungle_house_ai;

DELETE FROM wiki_article
WHERE article_id = x;



SELECT content FROM wiki_article WHERE article_id = 1;

ALTER TABLE wiki_article
ADD link TEXT;

CREATE TABLE article_links (
    link_id INT AUTO_INCREMENT PRIMARY KEY,
    article_id INT,
    label VARCHAR(100),
    url TEXT,
    FOREIGN KEY (article_id) REFERENCES wiki_article(article_id)
);


ALTER TABLE wiki_article
ADD sub_category VARCHAR(50);

UPDATE wiki_article
SET sub_category = 'SPRING KIOSK OPENING'
WHERE article_id = 28;

UPDATE wiki_article
SET sub_category = 'AEON OPENING'
WHERE article_id = 29;

USE jungle_house_ai;

INSERT INTO wiki_article (title, category, sub_category, content)
VALUES
('Opening SOP - Kiosk', 'SOP', 'Kiosk Opening', 'Kiosk steps...'),
('Opening SOP - Aeon', 'SOP', 'Aeon Roadshow Opening', 'Aeon steps...'),
('Opening SOP - Spring', 'SOP', 'Spring Roadshow Opening', 'Spring steps...');


#SET TABLE ORDER
ALTER TABLE wiki_article
ADD display_order INT;

USE jungle_house_ai;

UPDATE wiki_article SET display_order = 1 WHERE article_id = 28;
UPDATE wiki_article SET display_order = 2 WHERE article_id = 30;
UPDATE wiki_article SET display_order = 3 WHERE article_id = 29;
UPDATE wiki_article SET display_order = 4 WHERE article_id = 3;
UPDATE wiki_article SET display_order = 5 WHERE article_id = 4;
UPDATE wiki_article SET display_order = 6 WHERE article_id = 2;

#select table function
SELECT article_id, title FROM wiki_article;

#------------------------------------------------JHKCH KIOSK OPENING LIST------------------------------------------------------------------------
USE jungle_house_ai;

UPDATE wiki_article
SET title = 'JHKCH Kiosk Opening List'
WHERE article_id = 28;

USE jungle_house_ai;

UPDATE wiki_article
SET content = 'Opening SOP-JHKC Kiosk:

JHKC Kiosk Opening
1.	Clock in (TimeTec)
2.	Take photos (2 side) before rolling up blinds
3.	Unlock blinds and roll them up
o	Secure the blind cord to the kiosk pole as shown
 	[IMAGE] https://i.ibb.co/pjMKPL5V/image.png

	[IMAGE] https://i.ibb.co/whGT81j5/image.png

4.	Unlock all cabinet doors from B, C, E, F, K & L.
5.	Keep all the locks inside the cabinet
o	Refer to>>>>> Furniture Key Labelling
6.	Switch on display shelves (D, K & L) and ceiling lightings
7.	Take out two charged iPad, two terminal machine, iPad stand and powerbanks
8.	Ensure both tablets and terminal machines are charged
o	Click>>>>> Shopify POS app Opening
9.	Click Shopify app and start the session for both iPad
10.	Check Maybank app is logged in
o	Click>>>>> MBB QR auto Log out
11.	Terminal machine
o	Switch on
o	Press the return indicator
o	Press the Maybank logo indicator to start the terminal
12.	Charge two powerbanks
13.	Turn on all the device power
o	Click>>>>> How to switch on the Digital photo frame?
o	Switch on all the lights
[IMAGE] https://i.ibb.co/KcGx8tts/image.png
 
o	Chiller Light
[IMAGE] https://i.ibb.co/wZFv5zpm/image.png
 

4.	Use hook to take down blind next to the storeroom and place it inside the storeroom
 	[IMAGE] https://i.ibb.co/PZzF98jF/image.png

	[IMAGE] https://i.ibb.co/mrWdXtXq/image.png

 
	Use hook to attach up the blind cord to pillar
 			[IMAGE] https://i.ibb.co/ZzDNNDgy/image.png

5.	Set up the testers, tester spoon and tissue for both tester areas then make sure each tester area has a sales kit.
 	[IMAGE] https://i.ibb.co/YTRmhLS6/image.png
	
	[IMAGE] https://i.ibb.co/ZPFQqfm/image.png

	[IMAGE] https://i.ibb.co/pvP8q5Pn/image.png
 
 
6.	Set up sampling
7.	Arrange honey juices in fridge and check the expiry date of tester
8.	Set up Juice Tower: 
Click>>>>> Juice Tower Ice Pack 
Click>>>>> Charging Juice Tower
Click>>>>>Washing Juice Tower
9.	Update daily record sheet (beside fridge in storeroom)
[IMAGE] https://i.ibb.co/nqBts9Tp/image.png

10.	Update juice production calendar.(Another side of fridge in storeroom)
[IMAGE] https://i.ibb.co/wZrQqhJ9/image.png

11.	Unlock side door for Ice’s supply
	Click>>>>> Petty Cash Operation Sop
12.	Check preorder
13.	Take photo for opening. Opening Notes



Cleaning contractor:
14.	Take photos and post in the JH 14 – Kuching AJSB group.
15.	Switch ON all lightings and chiller’s LED lighting
16.	Wash all soaked towels in 2 (two) buckets; washed towels – Brown & Blue towels place at F1, Orange & Pink towels at Juice production counter
17.	Unlock and roll up all blinds
18.	Unlock door and cabinets doors
19.	Start cleaning works
o	Wash the cloths
o	Wipe all the tables
o	Vacuum floor
o	Mop floor
o	Vacuum decorations
o	Touch up decorations if needed
o	Clean tester raw honey and prevent it to be sticky
o	Set up the testers, tester spoon and tissue for both tester areas then make sure each tester area has a sales kit
7.	Place the vacuum as required and place battery in the cabinet (F3)
8.	Empty the water in the mop’s backet
9.	Restock and refill tasks
10.	Start tidying work after cleaning
11.	Display all Raw Honey testers on the Taster Stations
12.	Dispose the rubbish bag
You might also interested with this:
1.	
Related Question:
1.	


'
WHERE article_id = 28;



#----------------------------------------------------JHKC KIOSK CLOSING LIST------------------------------------------------------------------------------------------------------
USE jungle_house_ai;

UPDATE wiki_article
SET title = 'JHKCH Kiosk Closing'
WHERE article_id = 2;


USE jungle_house_ai;

UPDATE wiki_article
SET content = 'JHKCH Kiosk Closing:

Stocktake:
Restock all items up to quota
Click>>>>>Important Notes of Stocktake
Record all items taken on stock indicator white board (Deduct from previous total)

[IMAGE]https://i.imgur.com/Ff4Akel.jpeg

Press link below:
https://docs.google.com/spreadsheets/d/1NGMg28-Qz0Ila5M2QNur7zW5bGsFKpnqV2vRC01E_wY/edit?usp=drivesdk

Add all items written in stock indicator and record in the row of storeroom in google sheet:

[IMAGE]https://i.ibb.co/q3WP7Z0F/image.png

Count 1-14 and 23-34: if listed estimate, just estimate the number to save time

[IMAGE]https://i.ibb.co/dJcfKMYX/image.png

G. Count NR: 
    1. Measure all NR of first layer with black tie.
    
    [IMAGE]https://i.ibb.co/Zz9HZj0w/image.png
    
    2. Add the full NR together with the measured NR in black tie.
Refer to NR Record:
*Example: CB (6000) have two full jerry can, so 6000x2=12000 and add the CB jerry can with black tie.*
    
Click here to review how to count the jerry can. >>>Jerry Can Stocktake Guide

[IMAGE]https://i.ibb.co/d0TmmGKD/image.png

8.	Count all stock from Cabinet A to Cabinet M and record in google sheet. Click>>>>> Furniture Key Labelling
9.	Screenshot and send in JH 14-Kuching AJSB

Settlement:
1.	Update 10pm Sales Refer: Sales Report
2.	Print summary report
3.	Check sales amount for credit, debit, Maybank QR or others (Amex,Union Pay, Online Transfer)
4.	Print terminal settlement once tally
	1.	Click >>>>Credit Card Settlement
5.	Key in Tester and Staff drinks
6.	Daily Sales report (Refer to wiki for step-by-step guide)
	1.	Click >>>>Shopify POS app Closing
	2.	Click >>>> Updated Daily Sales Report
7.	Stapler Shopify settlement, terminal settlement, merchant copy receipts. Store in plastic bag labelling correct dates in lower level of cabinet F2.
	1.	Use this stapler in stationary box in level one of cabinet E3.
 
 [IMAGE]https://i.ibb.co/gMyQKWvy/image.png
 
8.	Download Daily Sales report from email and send to JH 14-Kuching AJSB
9.	Take picture of Staff report, send to JH 14-Kuching AJSB

Device:
1.	Keep & Charge 2 terminal and 2 tablets in cabinet F3
	1.	Format: Powerbank A-1 tablet and 1 terminal Powerbank B-1 tablet Black charger at the back-1 terminal
		[IMAGE]https://i.ibb.co/1tzThNCm/image.png
        
2.	Shut down kodak & Turn off switch in E3 (Kodak currently in Aeon)
3.	Turn off printer & Turn off switch in E3
4.	Bee Leader to restart CCTV Hard drive every Monday and Friday.
	[IMAGE]https://i.ibb.co/Y73FvVtM/image.png
    
Additional:
1.	Turn off outdoor switches (5)
	i.	Under citrus bloom (Open the wooden block and leave it aside ,do not put it back to cool down high temperature)
		[IMAGE]https://i.ibb.co/r2F702Ym/image.png
        
	ii.	behind cabinet L
		[IMAGE]https://i.ibb.co/XrS0jtSq/image.png
        
	iii.	behind cabinet K
		[IMAGE]https://i.ibb.co/8gF7Kt9f/image.png
        
	iv.	Under candle rack
		[IMAGE]https://i.ibb.co/HTkZYtWF/image.png
        
	v.	Behind Chiller
		[IMAGE]https://i.ibb.co/kgKnjRkK/image.png
        
2.	Place all outdoor items within kiosk area
3.	Keep own belongings in your shelf and out of sight.
4.	Bee Leader to make sure all keys returned in booth storage.
5.	Lock the store room back door:
	[IMAGE]https://i.ibb.co/ZpWCTHmx/image.png
    
6.	Pull down all blinds (12)
7.	Lock all blinds (12) Take the locks from bottom layer of Cabinet E3
8.	Lock all cabinets according to Furniture Key Labelling Take the keys from bottom layer of Cabinet E3
9.	Drain ice box & move to to storeroom door
	1.	🧊 Ice Bin Daily Closing Checklist
	2.	Draining Ice Tong
10.	Washing Juice Tower
11.	Take photo of closed kiosk
12.	Daily Incentive Declaration.
13.	Clock out (TimeTec)'
WHERE article_id = 2;

#----------------------------------------------------Opening SOP - Spring-----------------------------------------------------------------
USE jungle_house_ai;

UPDATE wiki_article
SET content = 'Opening SOP - QinSheng:

Steps
1.Clock in (TimeTec)
2.Take photo of the covered fabric of booth and send to group.
A. Sample
 	[IMAGE]

3.Open covered fabric, fold it and put inside the box.(Including all of the clips)
4.Put the box back to place:
[IMAGE]

5.Setup the QR code and put back the items on the top area.(Premium Wooden Spoon, Wooden Stirrer, Manager name card)
6.Take photo of the locked booth storage.
A.Sample
[IMAGE]

7.Unlock the booth storage.
8.Take out charged weighing scale.
A.Check battery level.
9.Take out charged iPad, terminal machine, iPad stand.
10.Charge powerbanks.
11.Terminal Machine
A.Switch on.
B.Press the return indicator
C.Press the Maybank logo indicator to start the terminal.
12.Charge terminal machine.
13.Wash both frontend and backend cloths and place on respectively.
14.Chiller
A.Get the keys from the booth storage to unlock padlock of the chiller.
B.Switch on the LED lighting and the lights of chiller.
C.Put the padlock and rope in the cover fabric’s box.
D.Place back the keys back in the booth storage after used.
E.Keep the chiller cleaned and cleared.
F.Honey juices is nicely lineups accordingly (date).
15.Turn on all the device power
A.Click >>>>> What to on every morning?
B.Click>>>>> How to switch on the Digital photo frame?
16.Click>>>>> Shopify POS app Opening
A.Click Shopify app and start the session for iPad.
B.Make sure printer is connected to start operation of the day. Click>>>>> Receipt printer preparation for opening
17.Clean the carpet
A.Use vacuum
	[IMAGE]

B.Throw the dust in rubbish bin
18.Ensure the table, rack and product display is dust free
A.Use duster or
	[IMAGE]

B.Vacuum

19.Clean the tester of raw honey and prevent it to be sticky.
20.Make sure the tester bottle bag and recycle bottle bag are nicely fold.
 [IMAGE]
21.Daily record sheet
A.Cleared it.
B.Write
i. date of the operating day,
ii. individual name and shift,
iii. staff’s juice
iv. honey juice’s date (add 5 days on operating day).
C.Make sure the daily record sheet doesn’t fell off; stick it back to place.
 	[IMAGE]
22.Check on the pre-order area. Remove the receipts or notes that are irrelevant. Check with the person in charge if unsure.
	[IMAGE]
23.Keep honey juice station cleaned. Serving tray dry and cleaned. Prepare the honey juice tester.
24.Take a photo of setup booth.
A. Sample
[IMAGE]

'
WHERE article_id = 30;

