
// https://coderwall.com/p/flonoa/simple-string-format-in-javascript
String.prototype.format = function () {
  var str = this;
  for (var i in arguments) {
    str = str.replace(new RegExp('\\{' + i + '\\}', 'gm'), arguments[i]);
  }
  return str;
}

$(document).ready(function () {
  $('#file').on('change',function (){
    // get the file names
    var filenames = " "
    const filelist = document.getElementById("file").files;
    for(var i = 0; i < filelist.length; i++){
      filenames += "'" + filelist[i].name + "' "
    }
    // replace the "Choose file..." label
    $(this).next('.uploadFile__label').html(filenames);
  })

  $('#upload').on('click', function () {
    var data = new FormData();
    // TODO: add support to upload multiple files
    $.each($('#file')[0].files, function (i, file) {
      data.append('file-' + i, file);
    });
    var pages = $('#pages').val() ? $('#pages').val() : "all";
    data.append('pages', pages);
    $.ajax({
      url: '/files',
      type: 'POST',
      cache: false,
      contentType: false,
      data: data,
      processData: false,
      success: function (data) {
        var redirect = '{0}//{1}/workspaces/{2}'.format(window.location.protocol, window.location.host, data['file_id']);
        window.location.replace(redirect);
      }
    });
  });
});
