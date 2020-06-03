import types

def initialize_models(nn):
    tf = nn.tf

    class ModelBase(nn.Saveable):
        def __init__(self, *args, name=None, **kwargs):
            super().__init__(name=name)
            self.layers = []
            self.built = False
            self.args = args
            self.kwargs = kwargs
            self.run_placeholders = None

        def _build_sub(self, layer, name):
            if isinstance (layer, list):
                for i,sublayer in enumerate(layer):
                    self._build_sub(sublayer, f"{name}_{i}")
            elif isinstance (layer, nn.LayerBase) or \
                    isinstance (layer, ModelBase):

                if layer.name is None:
                    layer.name = name

                if isinstance (layer, nn.LayerBase):
                    with tf.variable_scope(layer.name):
                        layer.build_weights()
                elif isinstance (layer, ModelBase):
                    layer.build()

                self.layers.append (layer)

        def xor_list(self, lst1, lst2):
            return  [value for value in lst1+lst2 if (value not in lst1) or (value not in lst2)  ]

        def build(self):
            with tf.variable_scope(self.name):

                current_vars = []
                generator = None
                while True:

                    if generator is None:
                        generator = self.on_build(*self.args, **self.kwargs)
                        if not isinstance(generator, types.GeneratorType):
                            generator = None

                    if generator is not None:
                        try:
                            next(generator)
                        except StopIteration:
                            generator = None

                    v = vars(self)
                    new_vars = self.xor_list (current_vars, list(v.keys()) )

                    for name in new_vars:
                        self._build_sub(v[name],name)

                    current_vars += new_vars

                    if generator is None:
                        break

            self.built = True

        #override
        def get_weights(self):
            if not self.built:
                self.build()

            weights = []
            for layer in self.layers:
                weights += layer.get_weights()
            return weights

        def get_layers(self):
            if not self.built:
                self.build()
            layers = []
            for layer in self.layers:
                if isinstance (layer, nn.LayerBase):
                    layers.append(layer)
                else:
                    layers += layer.get_layers()
            return layers

        #override
        def on_build(self, *args, **kwargs):
            """
            init model layers here

            return 'yield' if build is not finished
                        therefore dependency models will be initialized
            """
            pass

        #override
        def forward(self, *args, **kwargs):
            #flow layers/models/tensors here
            pass

        def __call__(self, *args, **kwargs):
            if not self.built:
                self.build()

            return self.forward(*args, **kwargs)

        def compute_output_shape(self, shapes):
            if not self.built:
                self.build()

            not_list = False
            if not isinstance(shapes, list):
                not_list = True
                shapes = [shapes]

            with tf.device('/CPU:0'):
                # CPU tensors will not impact any performance, only slightly RAM "leakage"
                phs = []
                for dtype,sh in shapes:
                    phs += [ tf.placeholder(dtype, sh) ]

                result = self.__call__(phs[0] if not_list else phs)

                if not isinstance(result, list):
                    result = [result]

                result_shapes = []

                for t in result:
                    result_shapes += [ t.shape.as_list() ]

                return result_shapes[0] if not_list else result_shapes

        def compute_output_channels(self, shapes):
            shape = self.compute_output_shape(shapes)
            shape_len = len(shape)

            if shape_len == 4:
                if nn.data_format == "NCHW":
                    return shape[1]
            return shape[-1]

        def build_for_run(self, shapes_list):
            if not isinstance(shapes_list, list):
                raise ValueError("shapes_list must be a list.")

            self.run_placeholders = []
            for dtype,sh in shapes_list:
                self.run_placeholders.append ( tf.placeholder(dtype, sh) )

            self.run_output = self.__call__(self.run_placeholders)

        def run (self, inputs):
            if self.run_placeholders is None:
                raise Exception ("Model didn't build for run.")

            if len(inputs) != len(self.run_placeholders):
                raise ValueError("len(inputs) != self.run_placeholders")

            feed_dict = {}
            for ph, inp in zip(self.run_placeholders, inputs):
                feed_dict[ph] = inp

            return nn.tf_sess.run ( self.run_output, feed_dict=feed_dict)

        def summary(self):
            layers = self.get_layers()
            layers_names = []
            layers_params = []

            max_len_str = 0
            max_len_param_str = 0
            delim_str = "-"

            total_params = 0

            #Get layers names and str lenght for delim
            for l in layers:
                if len(str(l))>max_len_str:
                    max_len_str = len(str(l))
                layers_names+=[str(l).capitalize()]

            #Get params for each layer
            layers_params = [ int(np.sum(np.prod(w.shape) for w in l.get_weights())) for l in layers ]
            total_params = np.sum(layers_params)

            #Get str lenght for delim
            for p in layers_params:
                if len(str(p))>max_len_param_str:
                    max_len_param_str=len(str(p))

            #Set delim
            for i in range(max_len_str+max_len_param_str+3):
                delim_str += "-"

            output = "\n"+delim_str+"\n"

            #Format model name str
            model_name_str = "| "+self.name.capitalize()
            len_model_name_str = len(model_name_str)
            for i in range(len(delim_str)-len_model_name_str):
                model_name_str+= " " if i!=(len(delim_str)-len_model_name_str-2) else " |"

            output += model_name_str +"\n"
            output += delim_str +"\n"


            #Format layers table
            for i in range(len(layers_names)):
                output += delim_str +"\n"

                l_name = layers_names[i]
                l_param = str(layers_params[i])
                l_param_str = ""
                if len(l_name)<=max_len_str:
                    for i in range(max_len_str - len(l_name)):
                        l_name+= " "

                if len(l_param)<=max_len_param_str:
                    for i in range(max_len_param_str - len(l_param)):
                        l_param_str+= " "

                l_param_str += l_param


                output +="| "+l_name+"|"+l_param_str+"| \n"

            output += delim_str +"\n"

            #Format sum of params
            total_params_str = "| Total params count: "+str(total_params)
            len_total_params_str = len(total_params_str)
            for i in range(len(delim_str)-len_total_params_str):
                total_params_str+= " " if i!=(len(delim_str)-len_total_params_str-2) else " |"

            output += total_params_str +"\n"
            output += delim_str +"\n"

            io.log_info(output)

    nn.ModelBase = ModelBase

    class PatchDiscriminator(nn.ModelBase):
        def on_build(self, patch_size, in_ch, base_ch=None, conv_kernel_initializer=None):            
            suggested_base_ch, kernels_strides = patch_discriminator_kernels[patch_size]
            
            if base_ch is None:
                base_ch = suggested_base_ch
            
            prev_ch = in_ch
            self.convs = []
            for i, (kernel_size, strides) in enumerate(kernels_strides):                
                cur_ch = base_ch * min( (2**i), 8 )
                
                self.convs.append ( nn.Conv2D( prev_ch, cur_ch, kernel_size=kernel_size, strides=strides, padding='SAME', kernel_initializer=conv_kernel_initializer) )
                prev_ch = cur_ch

            self.out_conv =  nn.Conv2D( prev_ch, 1, kernel_size=1, padding='VALID', kernel_initializer=conv_kernel_initializer)

        def forward(self, x):
            for conv in self.convs:
                x = tf.nn.leaky_relu( conv(x), 0.1 )
            return self.out_conv(x)

    nn.PatchDiscriminator = PatchDiscriminator

    class IllumDiscriminator(nn.ModelBase):
        def on_build(self, patch_size, in_ch, base_ch=None, conv_kernel_initializer=None):
            suggested_base_ch, kernels_strides = patch_discriminator_kernels[patch_size]            
            if base_ch is None:
                base_ch = suggested_base_ch
            
            prev_ch = in_ch
            self.convs = []
            for i, (kernel_size, strides) in enumerate(kernels_strides):
                cur_ch = base_ch * min( (2**i), 8 )
                self.convs.append ( nn.Conv2D( prev_ch, cur_ch, kernel_size=kernel_size, strides=strides, padding='SAME', kernel_initializer=conv_kernel_initializer) )
                prev_ch = cur_ch
                
            self.out1 = nn.Conv2D( 1, 1024, kernel_size=1, strides=1, padding='SAME', kernel_initializer=conv_kernel_initializer)
            self.out2 = nn.Conv2D( 1024, 1, kernel_size=1, strides=1, padding='SAME', kernel_initializer=conv_kernel_initializer)

        def forward(self, x):
            for conv in self.convs:
                x = tf.nn.leaky_relu( conv(x), 0.1 )   
            
            x = tf.reduce_mean(x, axis=nn.conv2d_ch_axis, keep_dims=True)
            
            x = self.out1(x)
            x = tf.nn.leaky_relu(x, 0.1 )   
            x = self.out2(x)
                   
            return x

    nn.IllumDiscriminator = IllumDiscriminator
    
patch_discriminator_kernels = \
    { 1  : (512, [ [1,1] ]),
      2  : (512, [ [2,1] ]),
      3  : (512, [ [2,1], [2,1] ]),
      4  : (512, [ [2,2], [2,2] ]),
      5  : (512, [ [3,2], [2,2] ]),
      6  : (512, [ [4,2], [2,2] ]),
      7  : (512, [ [3,2], [3,2] ]),
      8  : (512, [ [4,2], [3,2] ]),
      9  : (512, [ [3,2], [4,2] ]),
      10 : (512, [ [4,2], [4,2] ]),      
      11 : (512, [ [3,2], [3,2], [2,1] ]),
      12 : (512, [ [4,2], [3,2], [2,1] ]),
      13 : (512, [ [3,2], [4,2], [2,1] ]),
      14 : (512, [ [4,2], [4,2], [2,1] ]),
      15 : (512, [ [3,2], [3,2], [3,1] ]),
      16 : (512, [ [4,2], [3,2], [3,1] ]),
      17 : (512, [ [3,2], [4,2], [3,1] ]),
      18 : (512, [ [4,2], [4,2], [3,1] ]),      
      19 : (512, [ [3,2], [3,2], [4,1] ]),
      20 : (512, [ [4,2], [3,2], [4,1] ]),
      21 : (512, [ [3,2], [4,2], [4,1] ]),
      22 : (512, [ [4,2], [4,2], [4,1] ]),      
      23 : (256, [ [3,2], [3,2], [3,2], [2,1] ]),
      24 : (256, [ [4,2], [3,2], [3,2], [2,1] ]),
      25 : (256, [ [3,2], [4,2], [3,2], [2,1] ]),
      26 : (256, [ [4,2], [4,2], [3,2], [2,1] ]),      
      27 : (256, [ [3,2], [4,2], [4,2], [2,1] ]),      
      28 : (256, [ [4,2], [3,2], [4,2], [2,1] ]),
      29 : (256, [ [3,2], [4,2], [4,2], [2,1] ]),
      30 : (256, [ [4,2], [4,2], [4,2], [2,1] ]),      
      31 : (256, [ [3,2], [3,2], [3,2], [3,1] ]),
      32 : (256, [ [4,2], [3,2], [3,2], [3,1] ]),
      33 : (256, [ [3,2], [4,2], [3,2], [3,1] ]),
      34 : (256, [ [4,2], [4,2], [3,2], [3,1] ]),      
      35 : (256, [ [3,2], [4,2], [4,2], [3,1] ]),      
      36 : (256, [ [4,2], [3,2], [4,2], [3,1] ]),
      37 : (256, [ [3,2], [4,2], [4,2], [3,1] ]),
      38 : (256, [ [4,2], [4,2], [4,2], [3,1] ]),
    }