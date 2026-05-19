// static/js/search_engine.js
class SearchEngine {
    constructor(options) {
        this.inputDesktop = document.getElementById(options.inputIdDesktop || 'buscaRapidaInput');
        this.inputMobile = document.getElementById(options.inputIdMobile || 'buscaRapidaInputMobile');
        this.viewMode = options.viewMode || 'table';
        
        this.tabelaSemResultados = document.getElementById(options.tabelaSemResultadosId || 'tabela-sem-resultados-row');
        this.cardsSemResultados = document.getElementById(options.cardsSemResultadosId || 'cards-sem-resultados');
        this.backendSemResultados = document.getElementById(options.backendSemResultadosId || 'tabela-backend-sem-resultados');
        
        this.tableRowsSelector = options.tableRowsSelector || 'tbody tr.clickable-row';
        this.cardsSelector = options.cardsSelector || '.data-card';

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
        
        // Permite invocar a busca via evento (Ex: ao mudar um select dropdown)
        document.addEventListener('triggerSearch', () => {
            const query = this.inputDesktop ? this.inputDesktop.value.toLowerCase().trim() : (this.inputMobile ? this.inputMobile.value.toLowerCase().trim() : '');
            this.filter(query);
        });
    }

    filter(query) {
        const isMobile = window.innerWidth <= 768;
        let itemsToFilter = [];
        let displayStyle = '';

        if (isMobile) {
            itemsToFilter = document.querySelectorAll(this.tableRowsSelector);
            displayStyle = 'block';
        } else {
            if (this.viewMode === 'table') {
                itemsToFilter = document.querySelectorAll(this.tableRowsSelector);
                displayStyle = 'table-row';
            } else if (this.viewMode === 'cards' || this.viewMode === 'kanban') {
                itemsToFilter = document.querySelectorAll(this.cardsSelector);
                displayStyle = 'flex';
            }
        }

        let itemsVisiveis = 0;

        itemsToFilter.forEach(item => {
            let itemText = '';
            
            const spans = item.querySelectorAll('span.card-value, span.card-field-value');
            spans.forEach(span => { itemText += " " + span.textContent.toLowerCase(); });
            
            const h4 = item.querySelector('h4');
            if (h4) itemText += " " + h4.textContent.toLowerCase();

            if (isMobile || this.viewMode === 'table') {
                const situacaoSelect = item.querySelector('.situacao-dropdown');
                if (situacaoSelect && situacaoSelect.value) {
                    itemText += " " + situacaoSelect.value.toLowerCase();
                }
            }

            if (itemText.includes(query)) {
                item.style.setProperty('display', displayStyle, 'important');
                itemsVisiveis++;
            } else {
                item.style.setProperty('display', 'none', 'important');
            }
        });

        const noResults = (itemsVisiveis === 0);
        const isSearching = query.length > 0;

        if (isMobile || this.viewMode === 'table') {
            if (this.tabelaSemResultados) {
                this.tabelaSemResultados.style.setProperty('display', (isSearching && noResults) ? displayStyle : 'none', 'important');
            }
            if (this.backendSemResultados) {
                this.backendSemResultados.style.setProperty('display', isSearching ? 'none' : 'table-row', 'important');
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
            const cardsNaColuna = coluna.querySelectorAll('.data-card');
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