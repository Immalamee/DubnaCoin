document.addEventListener('DOMContentLoaded', function() {
    const initData = window.Telegram.WebApp.initData || '';
    const initDataUnsafe = window.Telegram.WebApp.initDataUnsafe || {};
    console.log('DOMContentLoaded event triggered');
    console.log('initData:', initData);

    const referrer_id = initDataUnsafe.start_param || null;
    console.log('referrer_id:', referrer_id);

    fetch('/process_init_data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData: initData, referrer_id: referrer_id })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Ответ от сервера:', data);
        if (data.success) {
            window.userToken = data.token;

            document.getElementById('welcome-message').innerHTML = `Добро пожаловать, <span class="text-primary">${data.username}</span>!`;
            document.getElementById('level').innerText = data.level;
            document.getElementById('coins').innerText = data.coins;
            const coinImage = document.getElementById('coin-image');
            coinImage.src = `/static/images/${data.current_skin}`;

            document.getElementById('coin-button').addEventListener('click', clickCoin);

            initializeApp();
        } else {
            document.getElementById('welcome-message').innerText = `Ошибка: ${data.error}`;
        }
    })
    .catch(error => {
        console.error('Ошибка сети:', error);
        document.getElementById('welcome-message').innerText = 'Ошибка сети. Пожалуйста, попробуйте позже.';
    });
});

function initializeApp() {
    document.getElementById('reportErrorButton').addEventListener('click', function() {
        const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
        errorModal.show();
    });

    document.getElementById('errorForm').addEventListener('submit', function(event) {
        event.preventDefault();
        const errorMessage = document.getElementById('errorMessage').value;

        fetch('/report_error', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ error_message: errorMessage, token: window.userToken })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const errorModal = bootstrap.Modal.getInstance(document.getElementById('errorModal'));
                errorModal.hide();

                document.getElementById('errorForm').reset();

                showToast('Спасибо! Ваше сообщение об ошибке отправлено.', 'success');
            } else {
                showToast('Ошибка при отправке сообщения. Пожалуйста, попробуйте снова.', 'danger');
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            showToast('Произошла ошибка. Пожалуйста, попробуйте позже.', 'danger');
        });
    });

    document.getElementById('shop-button').addEventListener('click', openShop);
    document.getElementById('friends-button').addEventListener('click', openFriends);

    const toastElList = [].slice.call(document.querySelectorAll('.toast'));
    toastElList.map(function(toastEl) {
        return new bootstrap.Toast(toastEl);
    });
}

function clickCoin() {
    fetch('/click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: window.userToken })
    })
    .then(response => response.json())
    .then(data => {
        if (data.coins !== undefined) {
            document.getElementById('coins').innerText = data.coins;
            const coinButton = document.getElementById('coin-button');
            coinButton.classList.add('flash');
            setTimeout(() => {
                coinButton.classList.remove('flash');
            }, 300);
        } else if (data.error) {
            showModal('Ошибка', data.error);
        }
    })
    .catch(error => {
        console.error('Ошибка при клике:', error);
        showModal('Ошибка', 'Произошла ошибка при обработке вашего клика. Пожалуйста, попробуйте позже.');
    });
}

function openShop() {
    window.location.href = `/shop?token=${encodeURIComponent(window.userToken)}`;
}

function openFriends() {
    window.location.href = `/friends?token=${encodeURIComponent(window.userToken)}`;
}

function showModal(title, message) {
    const modalTitle = document.getElementById('infoModalLabel');
    const modalBody = document.getElementById('modalBody');

    modalTitle.textContent = title;
    modalBody.textContent = message;

    const infoModal = new bootstrap.Modal(document.getElementById('infoModal'));
    infoModal.show();
}

function showToast(message, type) {
    const toastContainer = document.getElementById('toastContainer');
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-bg-${type} border-0 rounded-3 shadow-lg m-3`;
    toastEl.role = 'alert';
    toastEl.ariaLive = 'assertive';
    toastEl.ariaAtomic = 'true';
    toastEl.style.maxWidth = '350px';
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Закрыть"></button>
        </div>
    `;
    toastContainer.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl);
    toast.show();

    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
}

document.addEventListener('click', function(event) {
    if (event.target && event.target.id === 'copyButton') {
        copyReferralLink();
    }
});

function copyReferralLink() {
    const referralInput = document.getElementById('referralLinkInput');
    referralInput.select();
    referralInput.setSelectionRange(0, 99999);

    navigator.clipboard.writeText(referralInput.value).then(function() {
        showToast('Ссылка скопирована в буфер обмена!', 'success');
    }, function(err) {
        showModal('Ошибка', 'Ошибка при копировании ссылки: ' + err);
    });
}
