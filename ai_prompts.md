# HW 5 — Campus Customs Multi-Agent Team: AI Prompts

## Problem 1 — Create the AI Prompt Log

as with other assignments, create ai_prompts.md at the start of the assignment to log the prompts i give you. 

put one section for each problem including the problem number and title, at least one prompt i typed, and one follow up prompt as needed including a sentence as to why the follow up was needed.

## Problem 2 — Study the Campus Customs Database

great. copy the original file to data/campus_customs_new.db and start output/harness.md. for each table list the fields and one short line on why that table is important for the agents

## Problem 3 — Build the MCP Server

next, for problem 3:build the MCP server - write an MCP servicer in mcp_server using fastMCP that can talk to data/campus_customs_new.db. every agent in this assignment will use the tools in this MCP server - start with writing 3 tools we'll need for the tickets in the database. do not invent any information, only use information that is in the database

The first prompt asked only for the server and its tools, not for any documentation of them. I then gave this second prompt: in output/harness.md, list the three MCP tools and include which table it reads, which ticket it helps unlock and one sentence on why that tool is the right one for that ticket - tie the tool to the ticket as specifically and with as much detail with you can (do not be vague). add a short mcp_server/rreadme.md file that explains what the MCP server is for, which databser file it uses, and the three tools it has

## Problem 4 — Add the MCP Server to Vibe Coder and Test Each Tool

problem 4: add the mcp server to vibe coder and test each tool:  add the mcp server to this project so you can call the tools. save the connection JSON text in .mcp.json at the project root

The first prompt asked me to connect the server and test the tools but did not ask for the test results to be saved anywhere. I then gave this second prompt: once you'rre connected, if you havent already test each of the tools and save the evidence in output/MCP_smoke.json. for every tool include: the prompt, the tool name, the tool output (this has to match values in data/campus_customs_new.db)

## Problem 5 — Build the Agent Team and Grow the MCP Tools

okay now for problem 5: build the agent team and grow the MCP tools - build the agentic team using pydanticAI:boss, inventory, accounting, faicilities, and customer services. include prompts, models, and agent loops to allow them to delegate work to eachother with full connectivity. save the agent prompts in backend/prompts with one file per agent. put data types in backend/models.py and the agent files under backend. use as much detail as you can when writing the prompts.

The first prompt asked for the agents but not for the new MCP tools they would need, an audit trail, or any documentation. I then gave this second prompt: add any tools the agents need for the mcp server so they can work on the open tickets. wire the agents so they append to output/audit_trail.son, for each agent loop step record enough to audit later. append this file. in output/harness.md, list each agent and each MCP tool along with which table the tool uses. also add a short safety section wuth the guardrails a real business would want when agents touch real customers and money, plus limits that keep token use in check. update mcp_server/readme.md so the tool list matches

## Problem 6 — Plan the Three Tickets

Before we build the backend, I need to document the expected behavior for each open ticket. Can you show me all the open tickets in the database and where the expected sections are located? I want to fill those sections with which agent Boss should call first, which other agents should be involved, and which MCP tools they should use. Please don't implement the backend yet.

The first prompt only asked to see the open tickets and where the expected sections were; it did not give the workflows to put in them. I then gave this second prompt: I've written my expected workflows for the three open tickets below. Please add them to the corresponding expected sections in output/harness.md.

These are my predictions of how the agents should work together, not instructions to change their behavior.

Don't modify the agent code or run any tickets yet.

Ticket 101 — Bulldog T-shirt - Boss calls first: Inventory, because the customer ordered a T-shirt that is out of stock. Other agents involved:
•	Inventory checks whether the T-shirt is available and which vendor can restock it.
•	Accounting investigates the unpaid vendor invoice, checks available cash, and prepares a payment request if appropriate.
•	Customer Service drafts a message explaining the order status and any expected delay.
•	Boss determines how to proceed based on inventory availability, vendor restrictions, and payment approval.
MCP tools: list_tickets, check_stock, get_vendor_status, get_cash_position, request_payment, draft_customer_message, update_ticket. Human pay may be needed after approval.
Ticket 102 — Rent due Boss calls first: Facilities, because rent and leases fall under its responsibilities. Other agents involved:
•	Facilities checks the lease, rent amount, and due date.
•	Accounting checks available cash and prepares a payment request.
•	Boss determines whether the payment can proceed and ensures human approval is obtained.
MCP tools: list_tickets, get_leases, get_cash_position, request_payment, list_approvals, update_ticket. Human pay is needed to execute the payment.
Important: Rent is due in two days, not overdue. The team should recognize that distinction.
Ticket 103  Bulk hoodie discount Boss calls first: Inventory, because the customer wants 20 hoodies and the store only has eight available. Other agents involved:
•	Inventory checks the stock shortfall and restocking options.
•	Accounting evaluates the profit margin and determines whether the requested discount would be financially reasonable. It also checks whether restocking requires a purchase order.
•	Customer Service drafts a response to the Yale AI Club explaining the proposed discount and availability.
•	Boss makes the final decision about the discount and fulfillment plan.
MCP tools: list_tickets, check_stock, check_margin, get_vendor_status, get_cash_position, request_purchase_order (if appropriate), draft_customer_message, update_ticket. Human place_purchase_order may be needed.

## Problem 7 — Backend Routes

probme 7: backend routes. in backend/main.py use fastapi and add routes that do the following:

rreturn the three tickets and whether each is open orr resolved, take a ticket id and run the  agent on that ticket, return recent agent events (what each agent said and what tool it used to refresh the board), approve a payment or purchase after a human clicks approve, return the current checking balance from cash_accounts, reset the database to the original values when you want to try a fresh run.

from the backend/folder start the server with: uvicorn main:app --reload --port 8000

in output/harness.md, list each route in one line (what the URL is and what it does)

## Problem 8 — Agent Dashboard

okay now problem 8:agent dashboard - build the frontend dashboard in frontend/ with react + vite + typescript. the pge hsould call the routes you built in problem 7. at a minimum the board should list all three tickets, let me pick one ticket and strt the agent eam on it, show each agent and what they are syaying/doing while the ticket runs, mark a ticket resolved when the run finishes, show a short summary of ehat each agent did on that tiket, let a human apprrov a pay or purchase when asked, show the checking balance (it should drop after an approved pay). I'd like it to look like a modern business operations command center, with a clean navy, blue, and white color scheme.

At the top, show four summary cards: open tickets, resolved tickets, pending approvals, and current checking balance. Below that, I'd like a two-column layout. On the left, show the three tickets as cards with their status and a way to select and run each one. On the right, show the five agents and a live activity feed so I can see what they're doing as they work.

At the bottom, include a human approval section where I can approve or reject payments and purchase orders. When I approve a payment, the checking balance should update. Please include a short summary of what each agent did after a ticket finishes. Use simple icons, color-coded statuses, rounded cards, and subtle animations where helpful. Keep the implementation lightweight and avoid unnecessary libraries or complex features. Please connect everything to the existing FastAPI backend rather than using mock data for actual functionality.

The first prompt described the dashboard but did not say how the browser should reach the backend, how to start the board, or ask for the design to be written down. I then gave this second prompt: tell the front end to talk to your backend at http:/localhost:8000. on the backend allow the vite page origin (usually http://localhost:5173) so the browser is allowed to call those routes. start the board with npm run dev. write output/design.md with the dashboard layout etc that i just sent

## Problem 9 — Resolve the Tickets

problem 9:resolve the tickets - before testing the agents on a full run over the three tickets, rreset the working database data/campus_customs_new.db. note the starting checking balance. then run all three tickets on the boarrd until each is resolved. open output/desk_tickets.html. on each ticket tab, fill the actual section from this run:which agents worked, what the delegated, and which tools they used.

on the cash tab of the same output/desk_tickets.html, itemize the money. starting checking balance (after the reset. for each ticket: how cash changed when that ticket resolved and why (which pay/purchase, dollar amount, ending checking balane (it must match cash_accounts in the working database. this is extremely important, double check the math. 

then save output/rresolved_tickets.json for each ticket: id, final status, short outcome, what each agent contributed, and any human apprrovals

output/resolved_board.html - a page you can double click wiht a screenshot of the react board for each resolved ticket

append real runs to output/audit_trail.json. finish output/harness.md so it covers tables, MCP tools, the five agents, api routes, the dashboard, and safety rules

The first prompt asked me to open output/desk_tickets.html, but that page had never been built, because Problem 6 had not asked for it. I then gave these follow-up prompts: sorry in problem 6 i was supposed to tell you to build output/desk_tickets.html, a page i can double click with one tab per ticket. this is where we were supposed to save the actual section from the runs, with which agent worked, what they delegated and which tools the used

output/desk_tickets.html is also where we're supposed to save each ticket's expected section

so each ticket should have a tab with an expected section and an actual section

## Problem 10 — Reflection

can you create a reflections tab in output/desk_tickets.html and add the following for each ticket respectively in addition to the comparison you did at the bottom

1. How would you evaluate the performance of the agents on each ticket, and why?
Overall, I think the agents performed well, although there were some differences in how effectively they handled each ticket. For Ticket 101, the agents correctly identified that the T-shirt was out of stock and that an overdue $840 vendor invoice was preventing restocking. They coordinated between Inventory, Accounting, and Customer Service, considered the need to preserve enough cash for rent, and obtained human approval before paying the invoice and placing a purchase order. For Ticket 102, the agents correctly identified that rent was due in two days rather than overdue, confirmed sufficient cash was available, and requested human approval before making the payment. Ticket 103 was less successful initially. The agents correctly identified the inventory shortage and calculated the potential profit margin, but they initially proposed a $50 price without having received a specific discount request or approval. In the second run, they took a more cautious approach and declined to offer a discount without additional information. Overall, the agents were effective at gathering information and coordinating tasks, but the hoodie ticket showed some inconsistency in their decision-making.
2. For each ticket, how did Actual compare to the Expected plan you wrote earlier?
The agents generally followed the workflows I expected, although they sometimes involved additional tools or agents. For Ticket 101, the Boss contacted Inventory first, as expected, and involved Accounting and Customer Service to address the unpaid invoice and customer communication. The agents also used additional tools, including checking existing approvals and drafts and requesting a purchase order. For Ticket 102, the Boss correctly contacted Facilities first, and Accounting verified the available cash and prepared the payment request. Customer Service was also involved in drafting an acknowledgment, which I hadn't anticipated. For Ticket 103, the Boss contacted Inventory first, while Accounting evaluated margins and Customer Service drafted a response. However, the agents did not request a purchase order, and their recommendation changed between the first and second runs. Overall, the agents followed the expected division of responsibilities, but the actual workflows involved more coordination and some decisions I hadn't predicted.
3. What would have been simpler as one agent with tools, and why?
I think Ticket 102, the rent payment, would have been simpler to handle with a single agent rather than a multi-agent team. The task was relatively straightforward and involved checking the lease to confirm the rent amount and due date, verifying that sufficient cash was available, and preparing a payment request for human approval. A single agent with access to the lease, cash, and payment tools could have completed these steps without delegating between Facilities and Accounting. While having specialized agents helped separate responsibilities, it also added coordination that wasn't necessarily needed for such a routine task. The multi-agent approach was more valuable for tickets like the T-shirt order, where inventory availability, vendor restrictions, accounting, and customer communication were more interconnected.
4. Describe three new problems Campus Customs might face that this agent team could solve with the tools you built.
One problem the team could handle is a situation where a vendor has multiple outstanding invoices that are preventing the shop from placing new orders. Accounting could review the invoices and available cash, while Inventory could identify which products are affected by the vendor's restrictions. A second example would be a customer requesting a large order of a different product. Inventory could check available stock and restocking options, Accounting could evaluate the profitability of the order, and Customer Service could draft a response explaining pricing and availability. A third example would be preparing for upcoming rent payments across multiple leases. Facilities could identify upcoming obligations, Accounting could assess whether sufficient cash is available, and the Boss could determine which payments should be prepared for human approval. All three situations could be handled using the existing tools because they rely on information already available in the shop's database.
5. Describe three new problems Campus Customs might face that this agent team could not solve with the tools you built, and explain the tools and agents you would need.
One problem the team couldn't currently handle is a customer requesting a refund for a defective product. Although Customer Service could draft a response, the system doesn't have tools to verify past purchases, process returns, or issue refunds. This would require a Returns agent and additional tools for retrieving order histories, recording returns, and preparing refunds for human approval. A second problem would be a shipment that is delayed or lost in transit. Inventory can check vendor lead times, but it cannot track actual shipments or determine where an order is. A Shipping or Logistics agent with access to carrier tracking information would be needed. A third problem would be forecasting which products the shop should stock for the following month. While Inventory can check current stock levels, the existing tools don't provide historical sales trends or demand forecasts. A Sales Analytics agent with tools to retrieve historical sales data and forecast demand would allow the shop to make more informed purchasing decisions. These examples show that the effectiveness of the agent team depends not only on the agents themselves but also on the data and capabilities available through their tools.

## Problem 11 — Submit to GitHub

problem 11: submit to github - push the code to a public github repo to allow graders to clone it, and save the URL in output/github_url.txt. do not push my real .env to the github repo and do include both database files under data/ 

readme should explain:copy of orriinal b to the working copy when you need a clean run, start mcp server, start fastapi backend, start the react board, reset the db before a full three ticket run
