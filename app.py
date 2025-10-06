import os
from app import create_app

# Cria a instância da aplicação chamando a fábrica
app = create_app()

if __name__ == '__main__':
    # A lógica para rodar online (Hospedagem) ou localmente continua a mesma.
    # O site de hospedagem define a porta através de uma variável de ambiente PORT.
    port = int(os.environ.get("PORT", 5000))
    # O host '0.0.0.0' é necessário para que o app seja acessível de fora do container.
    # debug=False é recomendado para produção. Deixe True apenas para desenvolver.
    app.run(host='0.0.0.0', port=port, debug=True)