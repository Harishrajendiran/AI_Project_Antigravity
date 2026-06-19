document.addEventListener('DOMContentLoaded', () => {
    const tabMatches = document.getElementById('tab-btn-matches');
    const tabStandings = document.getElementById('tab-btn-standings');
    const viewMatches = document.getElementById('view-matches');
    const viewStandings = document.getElementById('view-standings');

    if (tabMatches && tabStandings && viewMatches && viewStandings) {
        tabMatches.addEventListener('click', () => {
            tabMatches.classList.add('active');
            tabStandings.classList.remove('active');
            viewMatches.classList.remove('hidden-view');
            viewStandings.classList.add('hidden-view');
        });

        tabStandings.addEventListener('click', () => {
            tabStandings.classList.add('active');
            tabMatches.classList.remove('active');
            viewStandings.classList.remove('hidden-view');
            viewMatches.classList.add('hidden-view');
        });
    }

    // Modal Open/Close Controls
    const openBtn = document.getElementById('open-entries-modal-btn');
    const closeBtn = document.getElementById('close-entries-modal-btn');
    const modal = document.getElementById('entries-modal');

    if (modal) {
        if (openBtn) {
            openBtn.addEventListener('click', () => {
                modal.style.display = 'flex';
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        }

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }

    // Reset Fixtures Confirmation Modal Control
    const resetTrigger = document.getElementById('btn-reset-trigger');
    const resetModal = document.getElementById('reset-confirm-modal');
    const closeResetModalBtn = document.getElementById('close-reset-modal-btn');
    const cancelResetBtn = document.getElementById('cancel-reset-btn');

    if (resetModal) {
        if (resetTrigger) {
            resetTrigger.addEventListener('click', () => {
                resetModal.style.display = 'flex';
            });
        }

        const hideResetModal = () => {
            resetModal.style.display = 'none';
        };

        if (closeResetModalBtn) {
            closeResetModalBtn.addEventListener('click', hideResetModal);
        }

        if (cancelResetBtn) {
            cancelResetBtn.addEventListener('click', hideResetModal);
        }

        resetModal.addEventListener('click', (e) => {
            if (e.target === resetModal) {
                hideResetModal();
            }
        });
    }

    // Matches & Fixtures Sub-tabs Filter Logic
    const filterBar = document.getElementById('matches-filter-bar');
    const matchCards = document.querySelectorAll('.match-card');

    if (filterBar && matchCards.length > 0) {
        const categoriesMap = new Map();
        
        function getCategoryInfo(stage, group) {
            if (stage === 'group' && group) {
                return { id: `group-${group}`, label: `Group ${group}` };
            }
            if (stage === 'league') {
                return { id: 'league', label: 'League Matches' };
            }
            if (stage === 'quarter') {
                return { id: 'quarter', label: 'Quarter-finals' };
            }
            if (stage === 'semi') {
                return { id: 'semi', label: 'Semi-finals' };
            }
            if (stage === 'final') {
                return { id: 'final', label: 'Finals' };
            }
            return { id: stage, label: stage.charAt(0).toUpperCase() + stage.slice(1) };
        }

        matchCards.forEach(card => {
            const stage = card.getAttribute('data-stage');
            const group = card.getAttribute('data-group');
            const cat = getCategoryInfo(stage, group);
            
            if (!categoriesMap.has(cat.id)) {
                categoriesMap.set(cat.id, cat.label);
            }
            card.setAttribute('data-cat-id', cat.id);
        });

        if (categoriesMap.size > 0) {
            const catOrder = ['group-A', 'group-B', 'group-C', 'group-D', 'league', 'quarter', 'semi', 'final'];
            const sortedKeys = Array.from(categoriesMap.keys()).sort((a, b) => {
                const specificIdxA = catOrder.indexOf(a);
                const specificIdxB = catOrder.indexOf(b);
                
                if (specificIdxA !== -1 && specificIdxB !== -1) {
                    return specificIdxA - specificIdxB;
                }
                if (a.startsWith('group-') && b.startsWith('group-')) {
                    return a.localeCompare(b);
                }
                const valA = specificIdxA !== -1 ? specificIdxA : 99;
                const valB = specificIdxB !== -1 ? specificIdxB : 99;
                return valA - valB;
            });

            sortedKeys.forEach(catId => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'sub-tab-btn';
                btn.setAttribute('data-cat-id', catId);
                btn.textContent = categoriesMap.get(catId);
                btn.addEventListener('click', () => {
                    filterBar.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    
                    let visibleIdx = 1;
                    matchCards.forEach(card => {
                        if (card.getAttribute('data-cat-id') === catId) {
                            card.style.display = '';
                            const snoSpan = card.querySelector('.sno-val');
                            if (snoSpan) {
                                snoSpan.textContent = visibleIdx++;
                            }
                        } else {
                            card.style.display = 'none';
                        }
                    });

                    // Save selected sub-tab in localStorage
                    const tourneyId = window.location.pathname.split('/').filter(Boolean).pop();
                    if (tourneyId) {
                        localStorage.setItem(`active_sub_tab_${tourneyId}`, catId);
                    }
                });
                filterBar.appendChild(btn);
            });

            // Activate saved sub-tab or default to the first one
            const tourneyId = window.location.pathname.split('/').filter(Boolean).pop();
            const savedCatId = tourneyId ? localStorage.getItem(`active_sub_tab_${tourneyId}`) : null;
            let activeBtn = null;
            
            if (savedCatId) {
                activeBtn = filterBar.querySelector(`.sub-tab-btn[data-cat-id="${savedCatId}"]`);
            }
            
            if (!activeBtn) {
                activeBtn = filterBar.querySelector('.sub-tab-btn');
            }
            
            if (activeBtn) {
                activeBtn.click();
            }
        }
    }

    // Score Feed Modal Control Logic
    const scoreModal = document.getElementById('score-modal');
    if (scoreModal) {
        const closeBtn = document.getElementById('close-score-modal-btn');
        const titleEl = document.getElementById('score-modal-title');
        const matchIdInput = document.getElementById('score-modal-match-id');
        const setNumInput = document.getElementById('score-modal-set-num');
        const currentSetSpan = document.getElementById('score-modal-current-set');
        const setsCountEl = document.getElementById('score-modal-sets-count');
        const numSetsInput = document.getElementById('score-modal-num-sets');
        const team1NameEl = document.getElementById('score-modal-team1-name');
        const team2NameEl = document.getElementById('score-modal-team2-name');
        const score1Input = document.getElementById('score-modal-score1');
        const score2Input = document.getElementById('score-modal-score2');
        const prevSetBtn = document.getElementById('score-modal-prev-set');
        const nextSetBtn = document.getElementById('score-modal-next-set');
        const decSetsBtn = document.getElementById('score-modal-dec-sets');
        const incSetsBtn = document.getElementById('score-modal-inc-sets');
        const randomBtn = document.getElementById('score-modal-random-btn');
        const deleteBtn = document.getElementById('score-modal-delete-btn');

        let activeMatchScores = [];
        let activeSetNum = 1;
        let totalSets = 3;
        let winningPoint = 21;

        function updateModalSetView() {
            setNumInput.value = activeSetNum;
            currentSetSpan.textContent = activeSetNum;
            setsCountEl.textContent = totalSets;
            numSetsInput.value = totalSets;

            // Load scores for the active set
            const scoreObj = activeMatchScores[activeSetNum - 1] || { team1: null, team2: null };
            score1Input.value = scoreObj.team1 !== null ? scoreObj.team1 : '';
            score2Input.value = scoreObj.team2 !== null ? scoreObj.team2 : '';

            // Disable/enable prev/next buttons
            prevSetBtn.disabled = activeSetNum <= 1;
            nextSetBtn.disabled = activeSetNum >= totalSets;
            
            // Style disabled navigation states to look appropriate
            prevSetBtn.style.opacity = activeSetNum <= 1 ? '0.3' : '1';
            prevSetBtn.style.cursor = activeSetNum <= 1 ? 'not-allowed' : 'pointer';
            nextSetBtn.style.opacity = activeSetNum >= totalSets ? '0.3' : '1';
            nextSetBtn.style.cursor = activeSetNum >= totalSets ? 'not-allowed' : 'pointer';

            // Disable/enable dec/inc sets count buttons
            decSetsBtn.disabled = totalSets <= 1;
            decSetsBtn.style.opacity = totalSets <= 1 ? '0.3' : '1';
            decSetsBtn.style.cursor = totalSets <= 1 ? 'not-allowed' : 'pointer';

            incSetsBtn.disabled = totalSets >= 5;
            incSetsBtn.style.opacity = totalSets >= 5 ? '0.3' : '1';
            incSetsBtn.style.cursor = totalSets >= 5 ? 'not-allowed' : 'pointer';
        }

        document.querySelectorAll('.scores-cell').forEach(cell => {
            cell.addEventListener('click', () => {
                const tr = cell.closest('.match-card');
                if (!tr) return;

                const matchId = tr.getAttribute('data-match-id');
                const team1 = tr.getAttribute('data-team1');
                const team2 = tr.getAttribute('data-team2');
                totalSets = parseInt(tr.getAttribute('data-num-sets')) || 3;
                winningPoint = parseInt(tr.getAttribute('data-winning-point')) || 21;
                const stageFull = tr.getAttribute('data-stage-full');
                const sno = tr.querySelector('.sno-val')?.textContent || '1';

                try {
                    activeMatchScores = JSON.parse(tr.getAttribute('data-scores') || '[]');
                } catch (e) {
                    activeMatchScores = [];
                }

                // Initialize scores array if empty/incorrect size
                while (activeMatchScores.length < totalSets) {
                    activeMatchScores.push({ team1: null, team2: null });
                }

                // Populate Modal Data
                titleEl.textContent = `${stageFull} - Match ${sno}`;
                matchIdInput.value = matchId;
                team1NameEl.textContent = team1.toUpperCase();
                team2NameEl.textContent = team2.toUpperCase();

                activeSetNum = 1;
                updateModalSetView();

                // Show Modal
                scoreModal.style.display = 'flex';
            });
        });

        // Close Modal
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                scoreModal.style.display = 'none';
            });
        }
        scoreModal.addEventListener('click', (e) => {
            if (e.target === scoreModal) {
                scoreModal.style.display = 'none';
            }
        });

        // Sets Count Decrement/Increment
        if (decSetsBtn) {
            decSetsBtn.addEventListener('click', () => {
                if (totalSets === 5) {
                    totalSets = 3;
                } else if (totalSets === 3) {
                    totalSets = 1;
                }
                if (activeSetNum > totalSets) {
                    activeSetNum = totalSets;
                }
                while (activeMatchScores.length > totalSets) {
                    activeMatchScores.pop();
                }
                updateModalSetView();
            });
        }

        if (incSetsBtn) {
            incSetsBtn.addEventListener('click', () => {
                if (totalSets === 1) {
                    totalSets = 3;
                } else if (totalSets === 3) {
                    totalSets = 5;
                }
                while (activeMatchScores.length < totalSets) {
                    activeMatchScores.push({ team1: null, team2: null });
                }
                updateModalSetView();
            });
        }

        function saveCurrentScoresToArray() {
            if (!activeMatchScores[activeSetNum - 1]) {
                activeMatchScores[activeSetNum - 1] = { team1: null, team2: null };
            }
            activeMatchScores[activeSetNum - 1].team1 = score1Input.value !== '' ? parseInt(score1Input.value, 10) : null;
            activeMatchScores[activeSetNum - 1].team2 = score2Input.value !== '' ? parseInt(score2Input.value, 10) : null;
        }

        if (score1Input && score2Input) {
            score1Input.addEventListener('input', saveCurrentScoresToArray);
            score2Input.addEventListener('input', saveCurrentScoresToArray);
        }

        // Helper to append all set scores as hidden inputs for bulk submission
        function prepareBulkSubmitForm() {
            const setNumInput = document.getElementById('score-modal-set-num');
            if (setNumInput) {
                setNumInput.removeAttribute('name');
            }

            // Remove any previously appended bulk input fields to avoid duplicates
            form.querySelectorAll('input[name^="score1_set"], input[name^="score2_set"]').forEach(el => el.remove());

            // Append new hidden inputs for all sets
            for (let i = 0; i < totalSets; i++) {
                const s = activeMatchScores[i] || { team1: null, team2: null };
                
                const input1 = document.createElement('input');
                input1.type = 'hidden';
                input1.name = `score1_set${i + 1}`;
                input1.value = s.team1 !== null ? s.team1 : '';
                form.appendChild(input1);

                const input2 = document.createElement('input');
                input2.type = 'hidden';
                input2.name = `score2_set${i + 1}`;
                input2.value = s.team2 !== null ? s.team2 : '';
                form.appendChild(input2);
            }
        }

        const form = document.getElementById('score-modal-form');
        if (form) {
            form.addEventListener('submit', (e) => {
                saveCurrentScoresToArray();
                prepareBulkSubmitForm();
            });
        }

        // Prev/Next Set Controls
        if (prevSetBtn && nextSetBtn) {
            prevSetBtn.addEventListener('click', () => {
                if (activeSetNum > 1) {
                    saveCurrentScoresToArray();
                    activeSetNum--;
                    updateModalSetView();
                }
            });
            nextSetBtn.addEventListener('click', () => {
                if (activeSetNum < totalSets) {
                    saveCurrentScoresToArray();
                    activeSetNum++;
                    updateModalSetView();
                }
            });
        }

        // Random generator
        if (randomBtn) {
            randomBtn.addEventListener('click', () => {
                const winner = Math.random() < 0.5 ? 1 : 2;
                const winScore = winningPoint;
                const loseScore = Math.floor(Math.random() * (winningPoint - 1));
                if (winner === 1) {
                    score1Input.value = winScore;
                    score2Input.value = loseScore;
                } else {
                    score1Input.value = loseScore;
                    score2Input.value = winScore;
                }
                saveCurrentScoresToArray();
            });
        }

        // Delete button clears the inputs and submits
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                activeMatchScores = activeMatchScores.map(() => ({ team1: null, team2: null }));
                score1Input.value = '';
                score2Input.value = '';
                prepareBulkSubmitForm();
                form.submit();
            });
        }
    }

    // Organizer control panel select/input dynamic validation
    const fixtureTypeDetail = document.getElementById('fixture-type-detail');
    const numGroupsDetail = document.getElementById('tourney-num-groups');
    const promotedPerGroupDetail = document.getElementById('tourney-promoted-per-group');

    if (numGroupsDetail && fixtureTypeDetail) {
        const updateFixtureOptionsDetail = () => {
            if (numGroupsDetail.value === "1") {
                fixtureTypeDetail.value = "leagues";
                Array.from(fixtureTypeDetail.options).forEach(opt => {
                    if (opt.value !== "leagues") {
                        opt.disabled = true;
                    }
                });
            } else {
                Array.from(fixtureTypeDetail.options).forEach(opt => {
                    opt.disabled = false;
                });
            }

            // Dynamically show/hide promoted_per_group based on fixture type
            if (promotedPerGroupDetail) {
                const isKnockout = (fixtureTypeDetail.value === 'groups_leagues');
                const groupInputParent = promotedPerGroupDetail.closest('.input-group');
                if (groupInputParent) {
                    if (isKnockout) {
                        groupInputParent.style.opacity = '1';
                        promotedPerGroupDetail.disabled = false;
                    } else {
                        groupInputParent.style.opacity = '0.3';
                        promotedPerGroupDetail.disabled = true;
                    }
                }
            }
        };

        numGroupsDetail.addEventListener('change', updateFixtureOptionsDetail);
        numGroupsDetail.addEventListener('input', updateFixtureOptionsDetail);
        fixtureTypeDetail.addEventListener('change', updateFixtureOptionsDetail);
        updateFixtureOptionsDetail();
    }

    // Export functionality (PDF & Word stage filtering)
    const stageSelect = document.getElementById('export-stage-select');
    const btnPdf = document.getElementById('btn-export-pdf');
    const btnWord = document.getElementById('btn-export-word');
    if (stageSelect && btnPdf && btnWord) {
        const tourneyId = window.location.pathname.split('/').filter(Boolean).pop();
        const getExportUrl = (format) => {
            const stage = stageSelect.value;
            let url = `/tournament/${tourneyId}/export/${format}`;
            if (stage) {
                url += '?stage=' + encodeURIComponent(stage);
            }
            return url;
        };
        btnPdf.addEventListener('click', () => {
            window.open(getExportUrl('pdf'), '_blank');
        });
        btnWord.addEventListener('click', () => {
            window.location.href = getExportUrl('word');
        });
    }

    // Toggle promotion status of a team (standings checks override) via Checkbox
    document.querySelectorAll('.promote-checkbox').forEach(cb => {
        cb.addEventListener('change', () => {
            const teamName = cb.getAttribute('data-team-name');
            const newPromoted = cb.checked;
            
            const csrfTokenInput = document.querySelector('input[name="csrf_token"]');
            const csrfToken = csrfTokenInput ? csrfTokenInput.value : '';
            const tourneyId = window.location.pathname.split('/').filter(Boolean).pop();
            
            fetch(`/tournament/${tourneyId}/promote_team`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `team_name=${encodeURIComponent(teamName)}&promote=${newPromoted ? '1' : '0'}&csrf_token=${csrfToken}`
            })
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    cb.checked = !newPromoted; // revert UI state on failure
                    if (data.error) {
                        alert(data.error);
                    }
                }
            })
            .catch(err => {
                console.error("Error toggling promotion status:", err);
                cb.checked = !newPromoted; // revert UI state on failure
                alert("Failed to update promotion status.");
            });
        });
    });
});
