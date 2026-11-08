import requests
import boto3
import uuid
from datetime import datetime

def lambda_handler(event, context):
    # La pagina https://ultimosismo.igp.gob.pe/productos/reportes-sismicos se arma con JavaScript,
    # por eso se consulta directamente el API JSON que usa la pagina para llenar la tabla
    anio = datetime.now().year
    url = "https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb/" + str(anio)
    headers = {'User-Agent': 'Mozilla/5.0'}

    # Realizar la solicitud HTTP
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code != 200:
        return {
            'statusCode': response.status_code,
            'body': 'Error al acceder a la pagina web'
        }
    sismos = response.json()

    # Si en el anio actual hay menos de 10 sismos, se completa con el anio anterior
    if len(sismos) < 10:
        url = "https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb/" + str(anio - 1)
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            sismos = sismos + response.json()

    if len(sismos) == 0:
        return {
            'statusCode': 404,
            'body': 'No se encontraron sismos'
        }

    # Ordenar del mas reciente al mas antiguo y quedarse con los 10 ultimos
    sismos.sort(key=lambda s: (str(s.get('fecha_local')), str(s.get('hora_local'))), reverse=True)
    sismos = sismos[:10]

    # Armar las filas (todo como texto, DynamoDB no acepta float)
    campos = ['codigo', 'fecha_local', 'hora_local', 'referencia', 'magnitud',
              'profundidad', 'latitud', 'longitud', 'intensidad']
    rows = []
    for s in sismos:
        row = {}
        for campo in campos:
            if s.get(campo) is not None:
                row[campo] = str(s.get(campo))
        rows.append(row)

    # Guardar los datos en DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('TablaSismosIGP')

    # Eliminar todos los elementos de la tabla antes de agregar los nuevos
    scan = table.scan()
    with table.batch_writer() as batch:
        for each in scan['Items']:
            batch.delete_item(
                Key={
                    'id': each['id']
                }
            )

    # Insertar los nuevos datos
    i = 1
    for row in rows:
        row['#'] = i
        row['id'] = str(uuid.uuid4())
        table.put_item(Item=row)
        i = i + 1

    # Retornar el resultado como JSON
    return {
        'statusCode': 200,
        'body': rows
    }
