from agent import ConstructionAgent

agent = ConstructionAgent()
print('Agent ready! Type your message (or quit to exit)')

while True:
    user_input = input('You: ')
    if user_input.lower() == 'quit':
        break
    response = agent.process_message(user_input)
    print(f'Sarah: {response}')
