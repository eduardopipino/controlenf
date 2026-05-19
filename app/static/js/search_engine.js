// static/js/search_engine.js
class SearchEngine {
    constructor(options) {
        this.inputDesktop = document.getElementById(options.inputIdDesktop || 'buscaRapidaInput');
        this.inputMobile = document.getElementById(options.inputIdMobile || 'buscaRapidaInputMobile');
        this.viewMode = options.viewMode || 'table';
        
        this.tabelaSemResultados = document.getElementById(options.tabelaSemResultadosId || 'tabela-sem-resultados-row');
        this.tableElement = document.getElementById(options.tableId || ''); // NOVO: Referência à tabela inteira
        this.cardsSemResultados = document.getElementById(options.cardsSemResultadosId || 'cards-sem-resultados');
        this.backendSemResultados = document.getElementById(options.backendSemResultadosId || 'tabela-backend-sem-resultados');
        
        this.tableRowsSelector = options.tableRowsSelector || 'tbody tr.clickable-row';
        this.cardsSelector = options.cardsSelector || '.data-card';
        this.extraRowsSelector = options.extraRowsSelector || null;

        this.init();
    }

    init() {
        const bindSearch = (input, otherInput) => {
            if (!input) return;
            const execute = (e) => {
                let query = '';
                if (e && e.target && e.target.tagName === 'INPUT') {
                    query = e.target.value.toLowerCase().trim();
                    if (otherInput) otherInput.value = e.target.value;
                } else {
                    query = input.value.toLowerCase().trim();
                }
                this.filter(query);
            };
            input.addEventListener('keyup', execute);
            input.addEventListener('search', execute);
            input.addEventListener('keydown', e => { 
                if (e.key === 'Escape') { input.value = ''; execute(e); }
            });
        };

        bindSearch(this.inputDesktop, this.inputMobile);
        bindSearch(this.inputMobile, this.inputDesktop);
        
        document.addEventListener('triggerSearch', () => {
            const query = this.inputDesktop ? this.inputDesktop.value.toLowerCase().trim() : (this.inputMobile ? this.inputMobile.value.toLowerCase().trim() : '');
            this.filter(query);
        });
    }

    filter(query) {
        const isMobile = window.innerWidth <= 768;
        const isSearching = query.length > 0;
        let itemsToFilter = [];
        let displayStyle = '';

        if (isMobile) {
            itemsToFilter = document.querySelectorAll(this.tableRowsSelector);
            displayStyle = 'block';
        } else {
            if (this.viewMode === 'table') {
                itemsToFilter = document.querySelectorAll(this.tableRowsSelector);
                displayStyle = 'table-row';
            } else {
                itemsToFilter = document.querySelectorAll(`${this.cardsSelector}:not(.card-quick-add-form)`);
                displayStyle = 'flex';
            }
        }

        let itemsVisiveis = 0;

        itemsToFilter.forEach(item => {
            if (item.id === 'inline-create-template') return;

            let itemText = "";
            const spans = item.querySelectorAll('span.card-value, span.card-field-value');
            spans.forEach(span => { itemText += " " + span.textContent.toLowerCase(); });
            const h4 = item.querySelector('h4');
            if (h4) itemText += " " + h4.textContent.toLowerCase();

            if (itemText.includes(query)) {
                if (isSearching) {
                    item.style.setProperty('display', displayStyle, 'important');
                } else {
                    item.style.display = ''; 
                }
                itemsVisiveis++;
            } else {
                item.style.setProperty('display', 'none', 'important');
            }
        });

        if (this.extraRowsSelector) {
            document.querySelectorAll(this.extraRowsSelector).forEach(el => {
                if (isSearching) {
                    el.style.setProperty('display', 'none', 'important');
                } else {
                    el.style.display = ''; 
                }
            });
        }

        const noResults = (itemsVisiveis === 0);

        // 3. Exibir mensagens de "Nenhum Resultado" e ESCONDER A TABELA INTEIRA
        if (isMobile || this.viewMode === 'table') {
            if (this.tabelaSemResultados) {
                if (isSearching && noResults) {
                    // Verifica se a mensagem é um TR ou um elemento solto (como P ou DIV)
                    const isTR = this.tabelaSemResultados.tagName === 'TR';
                    const displayVal = isTR ? (isMobile ? 'block' : 'table-row') : 'block';
                    
                    this.tabelaSemResultados.style.setProperty('display', displayVal, 'important');
                    
                    // Se a mensagem for solta (não-TR), então podemos esconder a tabela inteira!
                    if (!isTR && this.tableElement) {
                        this.tableElement.style.setProperty('display', 'none', 'important');
                    }
                } else {
                    this.tabelaSemResultados.style.setProperty('display', 'none', 'important');
                    // Restaura a tabela se a busca for limpa
                    if (this.tableElement) {
                        this.tableElement.style.display = ''; 
                    }
                }
            }
            if (this.backendSemResultados) {
                this.backendSemResultados.style.setProperty('display', isSearching ? 'none' : '', 'important');
            }
        } 
        
        if (!isMobile) {
            if (this.viewMode === 'cards' && this.cardsSemResultados) {
                this.cardsSemResultados.style.setProperty('display', (isSearching && noResults) ? 'block' : 'none', 'important');
            } else if (this.viewMode === 'kanban') {
                this.updateKanbanCounts(query);
            }
        }
    }

    updateKanbanCounts(query) {
        if (this.viewMode !== 'kanban' || window.innerWidth <= 768) return;
        const isSearching = query && query.length > 0;
        document.querySelectorAll('.kanban-column').forEach(coluna => {
            const cardsNaColuna = coluna.querySelectorAll('.data-card:not(.card-quick-add-form)');
            const totalCards = cardsNaColuna.length;
            let cardsEscondidos = 0;
            cardsNaColuna.forEach(card => { if (card.style.display === 'none') cardsEscondidos++; });
            let msgNenhumResultado = coluna.querySelector('.kanban-empty-msg');
            if (isSearching && totalCards > 0 && cardsEscondidos === totalCards) {
                if (!msgNenhumResultado) {
                    msgNenhumResultado = document.createElement('p');
                    msgNenhumResultado.className = 'kanban-empty-msg';
                    msgNenhumResultado.textContent = 'Nenhum resultado nesta coluna.';
                    coluna.querySelector('.kanban-cards').appendChild(msgNenhumResultado);
                }
            } else if (msgNenhumResultado) {
                msgNenhumResultado.remove();
            }
        });
    }
}