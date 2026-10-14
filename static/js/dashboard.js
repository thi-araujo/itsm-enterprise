/* ============================================================
   Dashboard avançado — ITSM Enterprise (Fase 3.6)

   Consome /api/v1/estatisticas/ para atualizar os números e desenhar os
   gráficos sem recarregar a página.

   Princípio: o servidor já renderizou os números na primeira carga (ver
   apps/dashboard/views.py). Este script apenas ATUALIZA o que está na tela.
   Se o fetch falhar, a página continua mostrando dados corretos em vez de
   zeros.

   A URL da API vem de um data-attribute em #dashboard-data — é o que permite
   este arquivo existir fora do template, sem precisar da tag {% url %}.
   ============================================================ */

(function () {
    'use strict';

    const config = document.getElementById('dashboard-data');
    if (!config) { return; }

    const STATS_URL     = config.dataset.statsUrl;
    const PODE_GERENCIAR = config.dataset.podeGerenciar === '1';
    const INTERVALO_MS  = 60000;

    // Cores alinhadas às variáveis do itsm.css (mesmas dos badges).
    const COR = {
        pending_approval: '#fbbf24',
        open:             '#60a5fa',
        in_progress:      '#22d3ee',
        waiting:          '#fbbf24',
        resolved:         '#34d399',
        closed:           '#94a3b8',
        rejected:         '#f87171',
        low:              '#34d399',
        medium:           '#fbbf24',
        high:             '#f87171',
        critical:         '#c4b5fd',
        linha:            '#3b82f6',
        texto:            '#c8d6f0',
        grade:            'rgba(28,37,64,.8)',
        suave:            '#4a5a7a',
    };

    const ROTULO_STATUS = {
        pending_approval: 'Aguardando Aprovação',
        open: 'Aberto', in_progress: 'Em Andamento', waiting: 'Aguardando',
        resolved: 'Resolvido', closed: 'Fechado', rejected: 'Rejeitado',
    };
    const ROTULO_PRIORIDADE = {
        low: 'Baixa', medium: 'Média', high: 'Alta', critical: 'Crítica',
    };
    // A ordem é fixa para a cor de cada fatia não trocar entre atualizações.
    const ORDEM_STATUS     = Object.keys(ROTULO_STATUS);
    const ORDEM_PRIORIDADE = Object.keys(ROTULO_PRIORIDADE);

    const graficos = {};

    /* ── Chart.js: padrões do tema escuro ───────────────────────── */

    if (window.Chart) {
        Chart.defaults.color = COR.suave;
        Chart.defaults.font.family = 'Sora, sans-serif';
        Chart.defaults.font.size = 11;
        Chart.defaults.plugins.legend.labels.boxWidth = 10;
        Chart.defaults.plugins.legend.labels.padding = 10;
        Chart.defaults.maintainAspectRatio = false;
    }

    function desenharRosca(id, rotulos, valores, cores) {
        const canvas = document.getElementById(id);
        if (!canvas || !window.Chart) { return; }

        if (graficos[id]) {
            // Atualizar em vez de recriar: recriar a cada 60s faria o
            // gráfico "piscar" e vazaria instâncias do Chart.js.
            graficos[id].data.labels = rotulos;
            graficos[id].data.datasets[0].data = valores;
            graficos[id].data.datasets[0].backgroundColor = cores;
            graficos[id].update();
            return;
        }
        graficos[id] = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: rotulos,
                datasets: [{
                    data: valores,
                    backgroundColor: cores,
                    borderColor: '#0e1320',
                    borderWidth: 2,
                }],
            },
            options: {
                cutout: '58%',
                plugins: { legend: { position: 'bottom' } },
            },
        });
    }

    function desenharBarras(id, rotulos, valores, cores) {
        const canvas = document.getElementById(id);
        if (!canvas || !window.Chart) { return; }

        if (graficos[id]) {
            graficos[id].data.labels = rotulos;
            graficos[id].data.datasets[0].data = valores;
            graficos[id].data.datasets[0].backgroundColor = cores;
            graficos[id].update();
            return;
        }
        graficos[id] = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: rotulos,
                datasets: [{
                    label: 'Chamados',
                    data: valores,
                    backgroundColor: cores,
                    borderRadius: 4,
                }],
            },
            options: {
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        grid: { color: COR.grade },
                        beginAtZero: true,
                        // Chamados são inteiros: sem isso o eixo mostraria 0,5.
                        ticks: { precision: 0 },
                    },
                },
            },
        });
    }

    function desenharLinha(id, rotulos, valores) {
        const canvas = document.getElementById(id);
        if (!canvas || !window.Chart) { return; }

        if (graficos[id]) {
            graficos[id].data.labels = rotulos;
            graficos[id].data.datasets[0].data = valores;
            graficos[id].update();
            return;
        }
        graficos[id] = new Chart(canvas, {
            type: 'line',
            data: {
                labels: rotulos,
                datasets: [{
                    label: 'Chamados abertos',
                    data: valores,
                    borderColor: COR.linha,
                    backgroundColor: 'rgba(59,130,246,.12)',
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2,
                }],
            },
            options: {
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } },
                    y: {
                        grid: { color: COR.grade },
                        beginAtZero: true,
                        ticks: { precision: 0 },
                    },
                },
            },
        });
    }

    /* ── Números dos cartões ─────────────────────────────────────── */

    function escrever(nome, valor) {
        const el = document.querySelector('[data-stat="' + nome + '"]');
        if (el) { el.textContent = valor; }
    }

    function atualizarCartoes(dados) {
        const porStatus = dados.por_status || {};
        escrever('total',       dados.total);
        escrever('open',        porStatus.open || 0);
        escrever('in_progress', porStatus.in_progress || 0);
        escrever('resolved',    dados.resolvidos);
        escrever('critical',    (dados.por_prioridade || {}).critical || 0);
        escrever('sla_risk',    dados.sla_vencido);

        if (!PODE_GERENCIAR) { return; }

        escrever('sla_em_risco', dados.sla_em_risco);
        escrever('sem_tecnico',  dados.sem_tecnico);

        const cumprimento = dados.sla_cumprimento || {};
        escrever('sla_percentual',
                 cumprimento.percentual === null || cumprimento.percentual === undefined
                     ? '—' : cumprimento.percentual + '%');

        const medio = dados.tempo_medio_resolucao_horas;
        escrever('tempo_medio',
                 medio === null || medio === undefined ? '—' : medio + 'h');
    }

    function atualizarGraficos(dados) {
        const porStatus = dados.por_status || {};
        // Só os status presentes entram, para não desenhar fatias de zero.
        const statusAtivos = ORDEM_STATUS.filter(k => porStatus[k]);
        desenharRosca('grafico-status',
                      statusAtivos.map(k => ROTULO_STATUS[k]),
                      statusAtivos.map(k => porStatus[k]),
                      statusAtivos.map(k => COR[k]));

        const porPrioridade = dados.por_prioridade || {};
        desenharBarras('grafico-prioridade',
                       ORDEM_PRIORIDADE.map(k => ROTULO_PRIORIDADE[k]),
                       ORDEM_PRIORIDADE.map(k => porPrioridade[k] || 0),
                       ORDEM_PRIORIDADE.map(k => COR[k]));

        const volume = dados.volume_diario || [];
        desenharLinha('grafico-volume',
                      volume.map(d => d.dia),
                      volume.map(d => d.total));
    }

    function marcarHorario(erro) {
        const el = document.getElementById('dash-atualizado');
        if (!el) { return; }
        if (erro) {
            el.textContent = '· falha ao atualizar (dados da última carga)';
            el.style.color = 'var(--itsm-warning)';
            return;
        }
        const agora = new Date();
        el.textContent = '· atualizado às ' +
            agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        el.style.color = 'var(--itsm-muted)';
    }

    /* ── Carga ───────────────────────────────────────────────────── */

    function periodoSelecionado() {
        const select = document.getElementById('dash-periodo');
        return select && select.value ? select.value : '';
    }

    function carregar() {
        const dias = periodoSelecionado();
        const url  = dias ? STATS_URL + '?days=' + encodeURIComponent(dias) : STATS_URL;

        fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(resposta => {
                if (!resposta.ok) { throw new Error('HTTP ' + resposta.status); }
                return resposta.json();
            })
            .then(dados => {
                atualizarCartoes(dados);
                atualizarGraficos(dados);
                marcarHorario(null);
            })
            .catch(() => {
                // Os números renderizados pelo servidor permanecem na tela.
                marcarHorario(true);
            });
    }

    const select = document.getElementById('dash-periodo');
    if (select) { select.addEventListener('change', carregar); }

    carregar();
    setInterval(carregar, INTERVALO_MS);
})();
