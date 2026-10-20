(function () {
  var menu = document.querySelector('#menu');
  var workspace = document.querySelector('#workspace');
  document.querySelector('#start').addEventListener('click', function () {
    menu.hidden = true; workspace.hidden = false;
  });
  document.querySelector('#back').addEventListener('click', function () {
    workspace.hidden = true; menu.hidden = false;
  });
  document.querySelector('#calculate').addEventListener('click', function () {
    var first = Number(document.querySelector('#first').value);
    var second = Number(document.querySelector('#second').value);
    document.querySelector('#result').textContent = Number.isFinite(first) && Number.isFinite(second) ? '结果：' + (first + second) : '请输入有效数字';
  });
})();
