/* static/js/main.js */

/**
 * Torna as linhas de uma tabela clicáveis, selecionando um radio button
 * e habilitando um botão de detalhes.
 * @param {string} tableId O ID da tabela a ser inicializada.
 * @param {string} radioButtonName O atributo 'name' dos radio buttons na tabela.
 * @param {string} detailsButtonId O ID do botão 'Detalhes...' a ser habilitado.
 * @param {string} detailsUrlTemplate O template da URL para o botão de detalhes, com 'REPLACE_ID' como placeholder.
 */
function initializeClickableTable(tableId, radioButtonName, detailsButtonId, detailsUrlTemplate) {
    const table = document.getElementById(tableId);
    // Se a tabela não existir na página atual, não faz nada.
    if (!table) {
        return;
    }

    const radioButtons = table.querySelectorAll(`input[name="${radioButtonName}"]`);
    const btnDetalhes = document.getElementById(detailsButtonId);
    const tableRows = table.querySelectorAll('tbody tr.clickable-row');

    tableRows.forEach(row => {
        row.addEventListener('click', () => {
            const radioButton = row.querySelector('input[type="radio"]');
            if (radioButton) {
                // Desmarca qualquer outro radio button que possa estar selecionado
                radioButtons.forEach(rb => {
                    if (rb !== radioButton) {
                        rb.checked = false;
                    }
                });
                
                // Marca o radio button da linha clicada
                radioButton.checked = true;

                // Dispara manualmente o evento 'change' para garantir que os listeners sejam acionados
                const event = new Event('change', { 'bubbles': true });
                radioButton.dispatchEvent(event);
            }
        });
    });

    radioButtons.forEach(radio => {
        radio.addEventListener('change', () => {
            // Habilita o botão de detalhes e define sua ação
            if (radio.checked) {
                btnDetalhes.disabled = false;
                btnDetalhes.onclick = () => {
                    // Pega o ID do radio selecionado e redireciona
                    const selectedId = document.querySelector(`input[name="${radioButtonName}"]:checked`).value;
                    window.location.href = detailsUrlTemplate.replace('REPLACE_ID', selectedId);
                };
            }
        });

        // Garante que o estado do botão esteja correto ao carregar a página
        if (radio.checked) {
            radio.dispatchEvent(new Event('change', { 'bubbles': true }));
        }
    });
}