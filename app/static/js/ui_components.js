// static/js/ui_components.js
document.addEventListener('DOMContentLoaded', function() {
    
    // --- 1. LÓGICA DO SELETOR DE VISUALIZAÇÃO ---
    const viewSelector = document.querySelector('.view-selector');
    if (viewSelector) {
        viewSelector.addEventListener('click', (e) => {
            const button = e.target.closest('.view-button');
            if (!button || button.classList.contains('active')) return;

            const selectedView = button.dataset.view;
            const endpoint = button.dataset.endpoint;

            if (endpoint) {
                // 1. Redireciona o usuário IMEDIATAMENTE (Corta a lentidão pela metade)
                const url = new URL(window.location.href);
                url.searchParams.set('view', selectedView);
                window.location.href = url.toString();

                // 2. Avisa o servidor em "segundo plano" (Fire-and-forget) sem travar a tela
                fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ view_mode: selectedView })
                }).catch(error => console.error('Erro em background:', error));
            }
        });
    }

    // --- 2. LÓGICA GERAL PARA FECHAMENTO DE MODAIS ---
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    });
    document.querySelectorAll('.btn-cancel-modal').forEach(button => {
        button.addEventListener('click', () => {
            const modal = button.closest('.modal-overlay');
            if (modal) modal.classList.remove('active');
        });
    });

    // --- 3. LÓGICA DE CLIQUE E EXPANDIR (MOBILE NATIVO) ---
    const clickableRows = document.querySelectorAll('.responsive-card-table .clickable-row[data-url], #tabelaControle .clickable-row[data-url], #tabelaPendencias .clickable-row[data-url]');
    clickableRows.forEach(row => {
        row.addEventListener('click', function(e) {
            if (window.innerWidth <= 768) { 
                if (!e.target.closest('.action-icon-link, .expand-card-btn, .situacao-dropdown, input, textarea, button, .card-priority-toggle, .btn-concluir-action')) {
                    window.location.href = this.dataset.url;
                }
            }
        });
    });

    document.querySelectorAll('.responsive-card-table .expand-card-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
            const row = this.closest('tr');
            if (row) {
                row.classList.toggle('card-expanded');
                this.textContent = row.classList.contains('card-expanded') ? 'Ver menos' : 'Ver mais';
            }
        });
    });

    // --- 4. LÓGICA DO MENU KEBAB (MOBILE) ---
    const kebabButton = document.getElementById('btnKebab');
    const kebabDropdown = document.querySelector('.kebab-menu-dropdown');
    if (kebabButton && kebabDropdown) {
        kebabButton.addEventListener('click', (e) => {
            e.stopPropagation();
            kebabDropdown.style.display = kebabDropdown.style.display === 'block' ? 'none' : 'block';
        });
        document.addEventListener('click', () => {
            kebabDropdown.style.display = 'none';
        });
    }
});