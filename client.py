import openai
import os
import time
import json
import requests
from dotenv import load_dotenv
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv()

# Configura tus credenciales
openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

def enviar_consulta(user_query: str):
    try:
        # Crear un thread
        thread = openai.beta.threads.create()
        
        # Añadir mensaje al thread
        message = openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_query
        )
        
        # Crear un run
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )
        
        # Esperar a que el assistant procese y devuelva respuesta
        max_attempts = 20
        attempts = 0
        while run.status not in ["completed", "failed", "cancelled"] and attempts < max_attempts:
            time.sleep(1)
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            attempts += 1

            # Handle requires_action state
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    arguments = tool_call.function.arguments
                    
                    if function_name == "buscar_vehiculos":
                        try:
                            # Parse the arguments (they come as a JSON string)
                            arguments_dict = json.loads(arguments)
                            
                            # Call your Vercel endpoint
                            response = requests.post(
                                "https://drenting-git-main-gustavos-projects-2cab746a.vercel.app/buscar_vehiculos",
                                json={"arguments": arguments_dict},
                                headers={"Content-Type": "application/json"},
                                timeout=10
                            )
                            
                            # Debug: Print the raw response
                            #print("Vercel API Response:", response.text)
                            
                            if response.status_code == 200:
                                output = response.json().get("output", "No output received")
                            else:
                                output = f"❌ API Error: {response.status_code} - {response.text}"
                            
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": output
                            })
                        
                        except Exception as e:
                            print("Tool call error:", str(e))
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": f"❌ Tool call failed: {str(e)}"
                            })
                
                # Submit all tool outputs back to the Assistant
                run = openai.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
                attempts = 0  # Reset attempts

        if run.status == "completed":
            # Obtener los mensajes del thread
            messages = openai.beta.threads.messages.list(
                thread_id=thread.id
            )
            # El último mensaje es la respuesta del assistant
            return messages.data[0].content[0].text.value
        else:
            return f"❌ No se pudo completar la respuesta. Estado: {run.status}"

    except Exception as e:
        return f"❌ Error: {e}"
    
# Bucle de conversación interactiva
def chat():
    print("\n🚗 Asistente de Renting de Vehículos 🚗")
    print("Escribe 'salir' para terminar.\n")
    while True:
        user_input = input("👤 Tú: ")
        if user_input.lower() in ["salir", "exit", "quit"]:
            print("\n👋 Conversación finalizada.")
            break
        respuesta = enviar_consulta(user_input)
        print(f"\n🤖 Assistant:\n{respuesta}\n")

if __name__ == "__main__":
    chat()