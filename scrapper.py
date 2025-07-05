import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

base_url = 'https://www.drenting.com/renting/page/{}'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

# Conexión a MongoDB
mongo_uri = os.getenv('MONGO_URI') or os.getenv('SCRAPER_MONGO_URI')
mongo_client = MongoClient(mongo_uri)

db = mongo_client['vehiculos']
coleccion = db['vehiculos']

def obtener_datos_tecnicos(soup):
    datos = {}
    propiedades = soup.find_all('div', class_='car-property')
    for prop in propiedades:
        spans = prop.find_all(['span', 'strong'])
        if len(spans) >= 2:
            clave = spans[0].get_text(strip=True).lower().replace(' ', '_')
            valor = spans[1].get_text(strip=True)
            datos[clave] = valor
    return datos


def obtener_informacion(soup):
    info_parrafos = []
    predesc = soup.find('div', class_='preDesc')
    if predesc:
        parrafos = predesc.find_all('p')
        for p in parrafos:
            for strong in p.find_all('strong'):
                strong.insert_before(' ')
                strong.insert_after(' ')
                strong.unwrap()
            texto = p.get_text()
            texto = re.sub(r'[\s\u00A0]+', ' ', texto).strip()
            if texto:
                info_parrafos.append(texto)
    return info_parrafos


def obtener_etiquetas_ambientales(soup):
    """Extrae las etiquetas ambientales del vehículo"""
    etiqueta_container = soup.find('div', class_='etiqueta-combinada-container')
    if not etiqueta_container:
        return None
    
    # Buscar la imagen de la etiqueta ambiental
    img_etiqueta = etiqueta_container.find('img', class_='environmental-label')
    if not img_etiqueta:
        return None
    
    # Extraer el valor del atributo alt de la imagen
    alt_text = img_etiqueta.get('alt', '')
    return alt_text if alt_text else None


def procesar_documento_vehiculo(vehiculo):
    """Procesa el documento del vehículo antes de guardarlo en MongoDB"""
    
    # Crear una copia del documento para no modificar el original
    vehiculo_procesado = vehiculo.copy()
    
    # Lista de atributos que deben contener al menos un dígito
    atributos_con_digitos = ['consumo', 'kilómetros', 'nº_marchas', 'plazas', 'potencia', 'puertas']
    
    # Procesar atributos que deben contener dígitos
    for atributo in atributos_con_digitos:
        if atributo in vehiculo_procesado:
            valor = vehiculo_procesado[atributo]
            if valor and isinstance(valor, str):
                # Verificar si contiene al menos un dígito
                if not re.search(r'\d', valor):
                    del vehiculo_procesado[atributo]
                else:
                    # Extraer números y convertir a entero
                    numeros = re.findall(r'\d+', valor)
                    if numeros:
                        vehiculo_procesado[atributo] = int(numeros[0])
    
    # Procesar el atributo año
    if 'año' in vehiculo_procesado:
        valor_año = vehiculo_procesado['año']
        if valor_año and isinstance(valor_año, str):
            numeros_año = re.findall(r'\d+', valor_año)
            if numeros_año:
                vehiculo_procesado['año'] = int(numeros_año[0])
    
    # Procesar el atributo informacion (lista)
    if 'informacion' in vehiculo_procesado:
        info = vehiculo_procesado['informacion']
        if isinstance(info, list):
            # Filtrar elementos vacíos de la lista
            info_filtrada = [item.strip() for item in info if item and item.strip()]
            if info_filtrada:
                vehiculo_procesado['informacion'] = info_filtrada
            else:
                del vehiculo_procesado['informacion']
        elif not info:
            del vehiculo_procesado['informacion']
    
    # Procesar el atributo precios (lista)
    if 'precios' in vehiculo_procesado:
        precios = vehiculo_procesado['precios']
        if isinstance(precios, list):
            # Filtrar elementos que no tengan importe o estén vacíos
            precios_filtrados = []
            for precio in precios:
                if isinstance(precio, dict) and 'importe' in precio and precio['importe'] is not None:
                    # Verificar que no haya valores vacíos o None en el elemento
                    tiene_valores_vacios = False
                    for valor in precio.values():
                        if valor is None or (isinstance(valor, str) and not valor.strip()) or valor == '':
                            tiene_valores_vacios = True
                            break
                    
                    if not tiene_valores_vacios:
                        precios_filtrados.append(precio)
            
            if precios_filtrados:
                vehiculo_procesado['precios'] = precios_filtrados
            else:
                del vehiculo_procesado['precios']
    
    # Eliminar atributos con valores vacíos o None
    atributos_a_eliminar = []
    for clave, valor in vehiculo_procesado.items():
        if valor is None or (isinstance(valor, str) and not valor.strip()) or valor == '':
            atributos_a_eliminar.append(clave)
    
    for atributo in atributos_a_eliminar:
        del vehiculo_procesado[atributo]
    
    return vehiculo_procesado


def obtener_descripcion(url, headers):
    # Usar requests para obtener la página primero
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return ''
    soup = BeautifulSoup(response.text, 'html.parser')
    predesc_ia = soup.find('div', class_='preDesc-ia')
    if not predesc_ia:
        return ''
    ia_content = predesc_ia.find('div', class_='ia-content')
    if not ia_content:
        return ''
    # Comprobar si existe el botón 'Ver más'
    show_more = ia_content.find(id='show-more-btn')
    if show_more:
        # Usar Selenium para obtener el texto completo
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-gpu')
            options.add_argument('--remote-debugging-port=9222')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-gpu')
            options.add_argument('--remote-debugging-port=9222')
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(url)
            wait = WebDriverWait(driver, 10)
            try:
                ver_mas = wait.until(EC.element_to_be_clickable((By.ID, 'show-more-btn')))
                ver_mas.click()
                time.sleep(0.2)  # Esperar a que se expanda el texto
            except (TimeoutException, NoSuchElementException):
                pass
            html_actualizado = driver.page_source
            driver.quit()
            soup = BeautifulSoup(html_actualizado, 'html.parser')
            predesc_ia = soup.find('div', class_='preDesc-ia')
            if not predesc_ia:
                return ''
            ia_content = predesc_ia.find('div', class_='ia-content')
            if not ia_content:
                return ''
        except Exception as e:
            print(f"Error con Selenium en {url}: {e}")
            return ''
    # Eliminar etiquetas <strong> y <p> dejando espacios
    for tag in ia_content.find_all(['strong', 'p']):
        tag.insert_before(' ')
        tag.insert_after(' ')
        tag.unwrap()
    descripcion = ia_content.get_text()
    descripcion = re.sub(r'[\s\u00A0]+', ' ', descripcion).strip()
    return descripcion


def extraer_precio_numerico(texto_precio):
    """Extrae el valor numérico del precio del texto"""
    if not texto_precio:
        return None
    # Buscar números seguidos de € o patrones de precio
    match = re.search(r'(\d+(?:\.\d+)?)\s*€', texto_precio.replace(',', '.'))
    if match:
        return float(match.group(1))
    return None


def obtener_precios_combinaciones(url):
    """Obtiene todos los precios para las diferentes combinaciones de duración y kilometraje"""
    precios = []
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        wait = WebDriverWait(driver, 10)

        # Esperar a que se cargue el formulario de variaciones
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'variations_form')))

        # Obtener los valores posibles de duración y kilometraje
        duraciones = [li.get_attribute('data-value') for li in driver.find_elements(By.CSS_SELECTOR, 'ul[data-id="duracion"] li.variable-item')]
        kilometrajes = [li.get_attribute('data-value') for li in driver.find_elements(By.CSS_SELECTOR, 'ul[data-id="km"] li.variable-item')]

        for duracion in duraciones:
            # Selecciona la duración
            li_duracion = driver.find_element(By.CSS_SELECTOR, f'ul[data-id="duracion"] li.variable-item[data-value="{duracion}"]')
            driver.execute_script("arguments[0].click();", li_duracion)
            time.sleep(0.2)
            # Siempre selecciona el primer kilometraje para forzar el reset
            if kilometrajes:
                li_km_reset = driver.find_element(By.CSS_SELECTOR, f'ul[data-id=\"km\"] li.variable-item[data-value=\"{kilometrajes[0]}\"]')
                driver.execute_script("arguments[0].click();", li_km_reset)
                time.sleep(0.2)
            for kilometraje in kilometrajes:
                try:
                    # Selecciona el kilometraje
                    li_km = driver.find_element(By.CSS_SELECTOR, f'ul[data-id=\"km\"] li.variable-item[data-value=\"{kilometraje}\"]')
                    driver.execute_script("arguments[0].click();", li_km)
                    time.sleep(0.2)

                    # Esperar a que el botón esté presente y visible
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'boton-form-desktop')))
                    boton_precio = driver.find_element(By.CLASS_NAME, 'boton-form-desktop')
                    span_precio = boton_precio.find_element(By.CLASS_NAME, 'span-price')
                    precio_texto = span_precio.get_attribute('innerText').strip()
                    if not precio_texto:
                        precio_texto = span_precio.get_attribute('textContent').strip()
                    precio_actual = extraer_precio_numerico(precio_texto)

                    # Precio anterior (opcional)
                    try:
                        precio_anterior_span = boton_precio.find_element(By.CLASS_NAME, 'before-price')
                        precio_anterior_val = extraer_precio_numerico(precio_anterior_span.text)
                    except NoSuchElementException:
                        precio_anterior_val = None

                    precio_dict = {
                        'duracion': int(duracion),
                        'kms': int(kilometraje),
                        'importe': precio_actual
                    }
                    if precio_anterior_val is not None:
                        precio_dict['importe_anterior'] = precio_anterior_val
                    precios.append(precio_dict)

                except Exception:
                    continue

        driver.quit()
    except Exception:
        try:
            driver.quit()
        except:
            pass
    return precios


def obtener_datos_vehiculo(coche):
    titulo_elem = coche.find('h2', class_='card-title')
    titulo = titulo_elem.get_text(strip=True) if titulo_elem else 'no disponible'

    enlace_elem = coche.find('a', class_='enlace-car')
    enlace = enlace_elem['href'] if enlace_elem else 'no disponible'

    # Para escrapear solo nuevos vehículos
    vehiculo_encontrado = coleccion.find_one({'url': enlace})
    if vehiculo_encontrado:
        return None

    vehiculo = {
        'nombre': titulo,
        'url': enlace,
        'scraped_at': datetime.now().isoformat()
    }

    if enlace != 'no disponible':
        try:
            response = requests.get(enlace, headers=headers)
            if response.status_code == 200:
                detalle_soup = BeautifulSoup(response.text, 'html.parser')
                vehiculo.update(obtener_datos_tecnicos(detalle_soup))
                vehiculo['informacion'] = obtener_informacion(detalle_soup)
                vehiculo['descripcion'] = obtener_descripcion(enlace, headers)
                vehiculo['etiquetas_ambientales'] = obtener_etiquetas_ambientales(detalle_soup)
                
                # Obtener todos los precios por combinaciones
                print(f"Obteniendo precios para {titulo}...")
                vehiculo['precios'] = obtener_precios_combinaciones(enlace)
                
        except Exception as e:
            print(f"Error obteniendo datos técnicos o información de {enlace}: {e}")
    
    return vehiculo


def guardar_en_mongodb(vehiculo):
    url = vehiculo.get('url')
    if not url:
        print('Vehículo sin URL, no se puede guardar en MongoDB.')
        return
    resultado = coleccion.update_one(
        {'url': url},
        {'$set': vehiculo},
        upsert=True
    )
    if resultado.matched_count == 0:
        print(f"Vehículo nuevo insertado: {url}")
    else:
        print(f"Vehículo actualizado: {url}")


def main():
    page = 1
    total_scrapeados = 0
    urls_primera_pagina = set()
    while True:
        print(f"\nScrapeando página {page}...")
        url = base_url.format(page)
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print("Fin del scraping. No más páginas.")
            break
        soup = BeautifulSoup(response.text, 'html.parser')
        coches = soup.find_all('div', class_='container-coches')
        if not coches:
            print("No hay más coches en esta página.")
            break
        urls_actuales = set()
        for coche in coches:
            enlace_elem = coche.find('a', class_='enlace-car')
            enlace = enlace_elem['href'] if enlace_elem else None
            if enlace:
                urls_actuales.add(enlace)
        if page == 1:
            urls_primera_pagina = urls_actuales.copy()
        else:
            # Si todas las URLs de la página actual están en la primera página, paramos
            if urls_actuales and urls_actuales.issubset(urls_primera_pagina):
                print("Detectada repetición de la primera página. Fin del scraping.")
                break
        for coche in coches:
            try:
                vehiculo = obtener_datos_vehiculo(coche)
                if vehiculo is None:
                    time.sleep(0.5)
                    continue

                vehiculo = procesar_documento_vehiculo(vehiculo)
                guardar_en_mongodb(vehiculo)
                total_scrapeados += 1
                print(f"Coches scrapeados hasta ahora: {total_scrapeados}")
                time.sleep(0.1)
            except Exception as e:
                print(f"Error procesando coche: {e}")
        page += 1
    print(f"Scraping completado. Total de coches procesados: {total_scrapeados}")

if __name__ == "__main__":
    main()