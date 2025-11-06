import openai, os
# configure openai api key
os.environ["OPENAI_API_KEY"]="sk-proj-yw-phteIZ4Tf77Y*************************************88888"

import asyncio
from pydantic import BaseModel, Field
import uuid
from agents import (
    Agent,
    HandoffOutputItem,
    ItemHelpers,
    MessageOutputItem,
    RunContextWrapper,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    TResponseInputItem,
    function_tool,
    handoff,
    trace,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from typing import List,Optional

class OrderedItem(BaseModel):
    item_name: str = Field(default="", description="Name of the ordered item")
    quantity: int = Field(default=0, description="Quantity of the ordered item")

class SupermarketAgentContext(BaseModel):
    order_id: str = Field(default="", description="Unique identifier for the customer's order")
    ordered_items: List[OrderedItem] = Field(default_factory=list, description="List of ordered items with their quantities")
    recipe: str = Field(default="", description="Recipe related to the ordered items")

# Tools

@function_tool(
    name_override="faq_lookup_tool", description_override="Lookup frequently asked questions.")
async def faq_lookup_tool(question: str) -> str:
    """
    tool used to resolve customer's common faq
    """
    question_lower = question.lower()
    general_answer= "This is a supermarket application, here you can simply place your orders and purchase the items if abailable or if you have any dish in your mind and you wanted to buy items to prepare that dish, you can discuss that here and this service will provide you the items list with the recipe that need to prepare the dish. "

    return general_answer

@function_tool
async def availability_check_tool( context: RunContextWrapper[SupermarketAgentContext], ordered_items: Optional[List[OrderedItem]] = None, order_id :Optional[str] = None
) -> str:
    
    # Update the context based on the customer's input
    context.context.ordered_items = ordered_items
    context.context.order_id = order_id
  
    available_items:list | None=None

    """
    ordered items comes form the context, those are cross checked with the data base.
    final available items updated in the available items list.
    """

    return ordered_items

@function_tool
async def recipe_tool( context: RunContextWrapper[SupermarketAgentContext], recipe: str = Field(default="", description="Recipe related to the ordered items")
) -> str:
    context.context.recipe = recipe
    pass

@function_tool
async def purchase_tool():

    return "Thankyou for purchasing"


# Agents 

faq_agent = Agent[SupermarketAgentContext](
    name="FAQ Agent",
    handoff_description="A helpful agent that can answer questions about the supermarket service.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are a FAQ agent. If you are speaking to a customer, you probably were transferred to from the triage agent.
    Use the following routine to support the customer.
    # Routine
    1. Identify the last question asked by the customer.
    2. Use the faq lookup tool to answer the question. Do not rely on your own knowledge.
    3. If you cannot answer the question, transfer back to the triage agent.""",
    tools=[faq_lookup_tool],
)


billing_agent=Agent[SupermarketAgentContext](
    name="Billing Agent",
    handoff_description="A helpful agent that handles the billing operation in the supermarket service.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are a brillient Billing Agent. If you are speaking to a customer, you probably were transferred to from the triage agent or the ordering agent.
    Use the following routine to support the customer.
    # Routine
    1. Get the final order passed from the ordering agent.
    2. Ask the customer about the payments methods.
    3. Pass the customer preffered payment method to the purchase tool.
    4. Once the purchasing finished return the cooking recipe to the customer.
    5. If you cannot answer the question, transfer back to the Triage Agent.
    6. if customer want to purchase more, transfer back to Order taking Agent""",
    tools=[purchase_tool],
    handoffs=[
    ],
)
    

ordering_agent = Agent[SupermarketAgentContext](
    name="Order taking Agent",
    handoff_description="A helpful agent that handles orders in the supermarket service.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are an Order taking Agent. If you are speaking to a customer, you probably were transferred to from the triage agent.
    Use the following routine to support the customer.
    # Routine
    1. Identify the last question asked by the customer.
    2. Get the items list that the customer want to purchase along with the quantity.
    3. Use the availability check tool to check the availability of the items in the list.
    4. Return the order confirmation message to the customer with the available items and ask them to give confirmation to proceed.
    5. Edit the changes in the order confirmation if customer wish and confirm the final order.
    6. handoff to biling agent with final order
    7. If you cannot answer the question, transfer back to the triage agent.""",
    tools=[availability_check_tool, ],
    handoffs=[
        billing_agent
    ],
)


recipe_agent=Agent[SupermarketAgentContext](
    name="Recipe Agent",
    handoff_description="A helpful agent that produce reipe and ingredients list for customer's desired meal in the supermarket service.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are a brillient Recipe Agent. If you are speaking to a customer, you probably were transferred to from the triage agent or the ordering agent.
    Use the following routine to support the customer.
    # Routine
    1. Identify the last question asked by the customer.
    2. If customer mentioned a meal ask him/her the number of portion they want to prepare.
    3. prepare the list of items needed to prepare the meal and pass that to Order taking agent.
    4. Update the recipe using Recipe tool.
    5. If you cannot answer the question, transfer back to the triage agent.""",
    tools=[recipe_tool],
    handoffs=[ordering_agent
    ],
)

triage_agent=Agent[SupermarketAgentContext](
    name="Triage Agent",
    handoff_description="A triage agent that can delegate a customer's request to the appropriate agent.",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "You are a helpful triaging agent. You can use your tools to delegate questions to other appropriate agents."
    ),
    handoffs=[
        faq_agent,ordering_agent , billing_agent, recipe_agent
    ],
)

faq_agent.handoffs.append(triage_agent)
billing_agent.handoffs.append(triage_agent)


async def main():
    current_agent: Agent[SupermarketAgentContext] = triage_agent
    input_items: list[TResponseInputItem] = []
    context = SupermarketAgentContext()

    order_id = uuid.uuid4().hex[:16]

    while True:
        user_input = input("Enter your message: ")
        with trace("Customer service", group_id=order_id):
            input_items.append({"content": user_input, "role": "user"})
            result = await Runner.run(current_agent, input_items, context=context)

            for new_item in result.new_items:
                agent_name = new_item.agent.name
                if isinstance(new_item, MessageOutputItem):
                    print(f"{agent_name}: {ItemHelpers.text_message_output(new_item)}")
                # elif isinstance(new_item, HandoffOutputItem):
                #     print(
                #         f"Handed off from {new_item.source_agent.name} to {new_item.target_agent.name}"
                #     )
                # elif isinstance(new_item, ToolCallItem):
                #     print(f"{agent_name}: Calling a tool")
                # elif isinstance(new_item, ToolCallOutputItem):
                #     print(f"{agent_name}: Tool call output: {new_item.output}")
                # else:
                #     print(f"{agent_name}: Skipping item: {new_item.__class__.__name__}")
            input_items = result.to_input_list()
            current_agent = result.last_agent


if __name__ == "__main__":
    asyncio.run(main())