# uvicorn delivery-metrics-api:app --host 0.0.0.0 --port 8000 --reload
# abrir local para testar a API http://localhost:8000/docs


from __future__ import print_function
import requests
import base64
from datetime import datetime
from fastapi import FastAPI
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


app = FastAPI()

def auth():
    # Abra o arquivo para leitura
    with open('auth.txt', 'r') as arquivo:
        # Leia e armazene cada linha em uma variável
        organization = arquivo.readline().strip()
        project = arquivo.readline().strip()
        personal_access_token = arquivo.readline().strip()

    # Codificar o token de acesso pessoal para a autenticação
    token = base64.b64encode(bytes(f":{personal_access_token}", "utf-8")).decode("utf-8")

    # Definir cabeçalhos para a solicitação
    headers = {
        "Authorization": f"Basic {token}"
    }
    return organization, project, headers


def get_query_results(organization, project, query_id, headers):
    task_ids = []
    # URL da API para extrair uma consulta específica
    # fonte: https://learn.microsoft.com/pt-br/rest/api/azure/devops/wit/wiql/query-by-wiql?view=azure-devops-rest-7.0&tabs=HTTP
    url = f'https://dev.azure.com/{organization}/{project}/_apis/wit/wiql/{query_id}?api-version=7.1-preview.2'

    # Fazer a solicitação GET
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        query_data = response.json()
        for query in query_data["workItems"]:
            task_ids.append(query['id'])
    else:
        print("Falha ao buscar a consulta. Código de status:", response.status_code)
    return task_ids


def get_state_changes(task_ids, project, organization, headers):
    # Lista para armazenar os estados das atualizações
    states = []
    for item in task_ids:
        #  fonte: https://learn.microsoft.com/pt-br/rest/api/azure/devops/wit/work-items/list?tabs=HTTP
        url_task = f'https://dev.azure.com/{organization}/{project}/_apis/wit/workItems/{item}/updates?api-version=7.0'
        response = requests.get(url_task, headers=headers)
        if response.status_code == 200:
            task_data = response.json()
            # print(json.dumps(task_data, indent=4))
            updates = task_data['value']

            for update in updates:
                try:
                    id = update['workItemId']
                    old_state = update['fields']['System.State']['oldValue']
                    new_state = update['fields']['System.State']['newValue']
                    old_date = update['fields']['Microsoft.VSTS.Common.StateChangeDate']['oldValue']
                    new_date = update['fields']['Microsoft.VSTS.Common.StateChangeDate']['newValue']
                    start_date = datetime.strptime(old_date, '%Y-%m-%dT%H:%M:%S.%fZ')
                    end_date = datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')
                    total_days = round(((end_date - start_date).total_seconds()) / 3600 / 24, 2)
                    hours_btw_dates = round(((end_date - start_date).total_seconds()) / 3600, 2)
                    states.append([id,
                                   old_state,
                                   start_date.strftime('%d/%m/%Y'),
                                   new_state,
                                   end_date.strftime('%d/%m/%Y'),
                                   total_days,
                                   hours_btw_dates
                                   ])
                except:
                    continue
        else:
            print(f"A solicitação falhou com o código de status: {response.status_code}")
    return states


def get_items_results(task_ids, organization, headers):
    processed_data = []
    fields = [
        "System.Id",
        "System.Title",
        "System.WorkItemType",
        "System.State",
        "System.AreaPath",
        "System.CreatedDate",
        "System.CreatedBy",
        "Microsoft.VSTS.Common.Priority",
        "Microsoft.VSTS.Common.ClosedDate",
        "Microsoft.VSTS.Common.ValueArea",
        "Custom.Customer"
    ]
    lista_fields = ','.join(fields)
    for item in task_ids:
        #  fonte: https://learn.microsoft.com/pt-br/rest/api/azure/devops/wit/work-items/list?tabs=HTTP
        url_task = f'https://dev.azure.com/{organization}/_apis/wit/workitems?ids={item}&fields={lista_fields}&api-version=7.2-preview.3'
        response = requests.get(url_task, headers=headers)
        if response.status_code == 200:
            task_data = response.json()
            id = task_data['value'][0]['fields']['System.Id']
            title = task_data['value'][0]['fields']['System.Title']
            type = task_data['value'][0]['fields']['System.WorkItemType']
            area_path = task_data['value'][0]['fields']['System.AreaPath']
            if 'System.CreatedDate' in task_data['value'][0]['fields']:
                created_date = task_data['value'][0]['fields']['System.CreatedDate']
            else:
                created_date = ''
            created_by = task_data['value'][0]['fields']['System.CreatedBy']['displayName']
            if 'Microsoft.VSTS.Common.Priority' in task_data['value'][0]['fields']:
                priority = task_data['value'][0]['fields']['Microsoft.VSTS.Common.Priority']
            else:
                priority = ''
            if 'Microsoft.VSTS.Common.ClosedDate' in task_data['value'][0]['fields']:
                closed_date = task_data['value'][0]['fields']['Microsoft.VSTS.Common.ClosedDate']
            else:
                closed_date = ''
            if 'Microsoft.VSTS.Common.ValueArea' in task_data['value'][0]['fields']:
                value_area = task_data['value'][0]['fields']['Microsoft.VSTS.Common.ValueArea']
            else:
                value_area = ''
            if 'Custom.Customer' in task_data['value'][0]['fields']:
                customer = task_data['value'][0]['fields']['Custom.Customer']
            else:
                customer = ''
            processed_data.append([id,
                                   title,
                                   type,
                                   area_path,
                                   created_date,
                                   created_by,
                                   priority,
                                   closed_date,
                                   value_area,
                                   customer])
        else:
            print("Falha ao buscar a consulta. Código de status:", response.status_code)
            # Salvar o arquivo
    return processed_data


def results(states_chages, processed_data):
    # Criando a lista combinada
    output = []
    # lista_combinada.append(processed_data[0] + states_chages[0][1:])

    # Mapeando os elementos com base no campo 'id'
    for item1 in states_chages:
        for item2 in processed_data:
            if item1[0] == item2[0]:
                output.append(item1 + item2[1:])

    # Exibindo a lista combinada resultante
    return output


def gcp_auth():
    # If modifying these scopes, delete the file token.json.
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', scopes)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def clear_sheets(creds, spreadsheet_id, range_name):
    try:
        service = build('sheets', 'v4', credentials=creds)

        # Crie o corpo da solicitação
        body = {}

        # Faça a solicitação para limpar a faixa especificada na planilha
        request = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name, body=body)
        response = request.execute()

    except HttpError as err:
        print(err)


def update_sheets(creds, spreadsheet_id, range_name, output):
    try:
        service = build('sheets', 'v4', credentials=creds)

        # Crie o corpo da solicitação
        body = {
            'values': output
        }

        # Faça a solicitação para escrever os valores na planilha
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='RAW', body=body).execute()

    except HttpError as err:
        print(err)


@app.get("/delivery-metrics/query/filter")
def update_delivery_metrics_dataset(query_id: str, spreadsheet_id: str, range_name: str):
    organization, project, headers = auth()
    task_ids = get_query_results(organization, project, query_id, headers)
    states_chages = get_state_changes(task_ids, project, organization, headers)
    processed_data = get_items_results(task_ids, organization, headers)
    output = results(states_chages, processed_data)
    creds = gcp_auth()
    clear_sheets(creds, spreadsheet_id, range_name)
    update_sheets(creds, spreadsheet_id, range_name, output)
    return 'Planilha Atualizada com Sucesso'
